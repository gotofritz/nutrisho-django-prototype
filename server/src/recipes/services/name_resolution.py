"""Resolve names typed into the recipe editor to `Ingredient`, `Tag`, `Cuisine` and `Unit` rows.

Names are unique ignoring case, so `Onion` typed on a phone that
auto-capitalises is the stored `onion`, not a second row; and a plural is a
display form, so `onions` is the stored `onion` too (#66). Lookups are
case-insensitive and keep the stored spelling; a miss creates an ingredient or
tag as typed, but never a cuisine or a unit, which only staff add.
Ingredients and tags are scoped to the recipe's owner: the global list plus
their own private rows (plan 011).
Every editor path goes through here rather than calling `get_or_create` on the
raw name, which matched case-sensitively and then hit the unique index (#34).
"""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F, Q, QuerySet
from django.db.models.functions import Lower

from recipes.models import Cuisine, Ingredient, IngredientAlias, Tag, Unit, UnitAlias
from recipes.models.cuisine import MAX_CUISINE_DEPTH, PATH_SEPARATOR
from recipes.utils.pluralise import pluralise


def _visible_ingredients(owner: AbstractBaseUser) -> QuerySet:
    """The global list plus `owner`'s private rows; never anyone else's."""
    return Ingredient.objects.filter(Q(owner__isnull=True) | Q(owner=owner))


def find_ingredient(name: str, *, owner: AbstractBaseUser) -> Ingredient | None:
    """The ingredient `owner` sees as `name`, ignoring case and surrounding space.

    A global row wins over the owner's private row of the same name: once staff
    have made a name global, that is the ingredient everyone means. On a miss,
    `name` may be the plural of a visible row (`onions` for `onion`, #66): a
    plural is a display form, never a row of its own (plan 009). Failing that,
    it may be an alias, or an alias's plural (`eggplants` for `aubergine`, plan
    008), which resolves to the alias's canonical row.
    """
    name = name.strip()
    visible = _visible_ingredients(owner).order_by(F("owner").asc(nulls_first=True), "pk")
    return (
        visible.filter(ingredient_name__iexact=name).first()
        or _by_plural(visible, name=name)
        or _by_alias(visible, name=name)
    )


def _by_plural(visible: QuerySet, *, name: str) -> Ingredient | None:
    """The first of `visible` whose plural, override or rule, is `name`.

    The rule lives in Python, so the database only narrows the candidates: an
    override that matches, or a rule-inflected row whose name shares `name`'s
    stem. Every rule ending adds at most three characters, so the singular
    always starts with `name` minus its last three.
    """
    lowered = name.lower()
    candidates = visible.filter(
        Q(plural_name__iexact=name)
        | Q(plural_name="", ingredient_name__istartswith=name[: max(len(name) - 3, 1)])
    )
    return next((row for row in candidates if row.plural.lower() == lowered), None)


def _by_alias(visible: QuerySet, *, name: str) -> Ingredient | None:
    """The canonical row of the alias spelling `name`, or of its plural.

    Narrowed by stem as `_by_plural` is. Only canonicals in `visible` count,
    though an alias's canonical is always global.
    """
    lowered = name.lower()
    candidates = IngredientAlias.objects.select_related("canonical").filter(
        canonical__in=visible,
        alias_name__istartswith=name[: max(len(name) - 3, 1)],
    )
    for alias in candidates.order_by("pk"):
        if lowered in {str(alias.alias_name).lower(), pluralise(str(alias.alias_name)).lower()}:
            return alias.canonical
    return None


def resolve_ingredient(name: str, *, owner: AbstractBaseUser) -> Ingredient:
    """`find_ingredient`, or on a miss a new row private to `owner`, as typed.

    Private until staff promote it (plan 011): an unknown name is one user's
    vocabulary, typos included, and must not appear in anyone else's editor.
    """
    found = find_ingredient(name, owner=owner)
    if found is not None:
        return found
    return Ingredient.objects.create(ingredient_name=name.strip(), owner=owner)


SUGGESTION_LIMIT = 20


def suggest_ingredient_names(
    text: str, *, owner: AbstractBaseUser, limit: int = SUGGESTION_LIMIT
) -> list[str]:
    """Up to `limit` names `owner` sees that match `text`, for the editor's autocomplete (#80).

    Names starting with `text` come first, then names containing it, each sorted
    ignoring case. A name `owner` has both globally and privately is offered
    once, in the global spelling, which is the row it would resolve to.
    """
    text = text.strip()
    if not text:
        return []
    visible = _visible_ingredients(owner).order_by(
        Lower("ingredient_name"), F("owner").asc(nulls_first=True), "ingredient_name"
    )
    starts = visible.filter(ingredient_name__istartswith=text)
    contains = visible.filter(ingredient_name__icontains=text).exclude(
        ingredient_name__istartswith=text
    )
    found: dict[str, str] = {}
    for matches in (starts, contains):
        # A name appears at most twice (global and private), so twice the limit
        # always leaves `limit` distinct names.
        for name in matches.values_list("ingredient_name", flat=True)[: limit * 2]:
            found.setdefault(name.lower(), name)
            if len(found) == limit:
                return list(found.values())
    return list(found.values())


def find_tag(name: str, *, owner: AbstractBaseUser) -> Tag | None:
    """The tag `owner` sees as `name`: global first, then their own, ignoring case."""
    return (
        Tag.objects.filter(Q(owner__isnull=True) | Q(owner=owner), tag__iexact=name.strip())
        .order_by(F("owner").asc(nulls_first=True))
        .first()
    )


def resolve_tag(name: str, *, owner: AbstractBaseUser) -> Tag:
    """`find_tag`, or on a miss a new tag private to `owner`, as typed (plan 011)."""
    found = find_tag(name, owner=owner)
    if found is not None:
        return found
    return Tag.objects.create(tag=name.strip(), owner=owner)


def find_cuisine(text: str) -> Cuisine | None:
    """The cuisine node `text` names, ignoring case; never creates one.

    `text` is a dotted path from the area down (`med.italy.sicily`), or a bare
    node name when exactly one node has it (`sicily`, but not `north`, which
    sits under thailand, vietnam and mexico). Cuisines are a curated global
    tree (plan 011): the editor picks from it and staff add to it in admin.
    """
    parts = [part.strip() for part in text.strip().split(PATH_SEPARATOR)]
    if not all(parts):
        return None
    node = None
    for part in parts:
        node = Cuisine.objects.filter(parent=node, cuisine__iexact=part).first()
        if node is None:
            break
    if node is not None or len(parts) > 1:
        return node
    named = list(Cuisine.objects.filter(cuisine__iexact=parts[0])[:2])
    return named[0] if len(named) == 1 else None


def cuisine_paths() -> list[str]:
    """Every node's dotted path, sorted: the editor's cuisine suggestions."""
    nodes = {c.pk: c for c in Cuisine.objects.all()}
    paths = []
    for cuisine in nodes.values():
        names = [str(cuisine.cuisine)]
        parent_id = cuisine.parent_id
        while parent_id is not None and parent_id in nodes and len(names) <= MAX_CUISINE_DEPTH:
            names.insert(0, str(nodes[parent_id].cuisine))
            parent_id = nodes[parent_id].parent_id
        paths.append(PATH_SEPARATOR.join(names))
    return sorted(paths, key=str.lower)


def find_unit(text: str) -> Unit | None:
    """The unit `text` spells, ignoring case, space and a trailing full stop; never creates one.

    `Tbsp`, `tbsp.`, `tablespoons` and `tbs` are all `tbsp` (#67): the unit's
    name, its plural, an alias, or an alias's plural, in that order. The
    vocabulary is a few dozen rows, so plurals are matched in Python.
    """
    name = " ".join(text.split()).removesuffix(".").strip()
    if not name:
        return None
    lowered = name.lower()
    exact = Unit.objects.filter(name__iexact=name).first()
    if exact is not None:
        return exact
    plural = next((u for u in Unit.objects.all() if u.plural.lower() == lowered), None)
    if plural is not None:
        return plural
    for alias in UnitAlias.objects.select_related("unit").order_by("pk"):
        if lowered in {str(alias.alias_name).lower(), pluralise(str(alias.alias_name)).lower()}:
            return alias.unit
    return None


def unit_names() -> list[str]:
    """Canonical unit names to suggest in the recipe editor, sorted ignoring case."""
    return sorted(Unit.objects.values_list("name", flat=True), key=lambda n: (n.lower(), n))
