"""Resolve names typed into the recipe editor to `Ingredient`, `Tag`, `Cuisine` and `Unit` rows.

Names are unique ignoring case, so `Onion` typed on a phone that
auto-capitalises is the stored `onion`, not a second row; and a plural is a
display form, so `onions` is the stored `onion` too (#66). Lookups are
case-insensitive and keep the stored spelling; a miss creates an ingredient,
tag, unit or cuisine as typed.
Each is scoped to the recipe's owner: the global list plus their own private
rows (plan 011, #154, #171).
Every editor path goes through here rather than calling `get_or_create` on the
raw name, which matched case-sensitively and then hit the unique index (#34).
"""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F, Q, QuerySet
from django.db.models.functions import Lower

from recipes.models import Cuisine, Ingredient, IngredientAlias, Tag, Unit, UnitAlias
from recipes.models.cuisine import CUISINE_MAX_LENGTH, MAX_CUISINE_DEPTH, PATH_SEPARATOR
from recipes.utils.pluralise import pluralise
from recipes.utils.unit_words import not_a_unit


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


def resolve_ingredient(
    name: str, *, owner: AbstractBaseUser, defaults: dict[str, str] | None = None
) -> Ingredient:
    """`find_ingredient`, or on a miss a new row private to `owner`, as typed.

    Private until staff promote it (plan 011): an unknown name is one user's
    vocabulary, typos included, and must not appear in anyone else's editor.
    `defaults` are further columns for a new row, such as an import's
    `plural_name` (#78); a row that is found keeps its own.
    """
    found = find_ingredient(name, owner=owner)
    if found is not None:
        return found
    return Ingredient.objects.create(ingredient_name=name.strip(), owner=owner, **(defaults or {}))


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


class CuisineNameError(ValueError):
    """A typed cuisine that names no node and cannot be made into one."""


def _visible_cuisines(owner: AbstractBaseUser | None) -> QuerySet:
    """The global tree plus `owner`'s own nodes, global first; the global tree alone for None."""
    visible = Q(owner__isnull=True) if owner is None else Q(owner__isnull=True) | Q(owner=owner)
    return Cuisine.objects.filter(visible).order_by(F("owner").asc(nulls_first=True), "pk")


def _cuisine_parts(text: str) -> list[str]:
    return [part.strip() for part in text.strip().split(PATH_SEPARATOR)]


def find_cuisine(text: str, *, owner: AbstractBaseUser | None = None) -> Cuisine | None:
    """The cuisine node `text` names, ignoring case; never creates one.

    `text` is a dotted path from the area down (`med.italy.sicily`), or a bare
    node name when exactly one node has it (`sicily`, but not `north`, which
    sits under thailand, vietnam and mexico). Only the global tree and
    `owner`'s own nodes are seen, and a global node wins over a private one of
    the same name.
    """
    parts = _cuisine_parts(text)
    if not all(parts):
        return None
    visible = _visible_cuisines(owner)
    node = None
    for part in parts:
        node = visible.filter(parent=node, cuisine__iexact=part).first()
        if node is None:
            break
    if node is not None or len(parts) > 1:
        return node
    named = list(visible.filter(cuisine__iexact=parts[0])[:2])
    return named[0] if len(named) == 1 else None


def resolve_cuisine(text: str, *, owner: AbstractBaseUser) -> Cuisine | None:
    """`find_cuisine`, or on a miss the node made private to `owner`; None when blank.

    A path's missing levels are made inside the deepest node it names that
    `owner` sees (`med.italy.marche` inside the global `med.italy`), and an
    unknown bare name becomes an area of their own. Raises `CuisineNameError`,
    making nothing, for a bare name more than one node has, a blank part, a
    name too long, or a path deeper than three levels. Call inside the
    write's transaction.
    """
    if not text.strip():
        return None
    found = find_cuisine(text, owner=owner)
    if found is not None:
        return found
    _check_cuisine(text, owner=owner)
    visible = _visible_cuisines(owner)
    node = None
    for part in _cuisine_parts(text):
        parent, node = node, visible.filter(parent=node, cuisine__iexact=part).first()
        if node is None:
            node = Cuisine.objects.create(cuisine=part, parent=parent, owner=owner)
    return node


def _check_cuisine(text: str, *, owner: AbstractBaseUser) -> None:
    parts = _cuisine_parts(text)
    if not all(parts):
        msg = f"“{text.strip()}” has an empty part: write it as area.region.subregion."
        raise CuisineNameError(msg)
    if len(parts) > MAX_CUISINE_DEPTH:
        msg = f"Cuisines go at most {MAX_CUISINE_DEPTH} levels deep (area.region.subregion)."
        raise CuisineNameError(msg)
    if any(len(part) > CUISINE_MAX_LENGTH for part in parts):
        msg = f"A cuisine name can be at most {CUISINE_MAX_LENGTH} characters long."
        raise CuisineNameError(msg)
    if len(parts) == 1 and _visible_cuisines(owner).filter(cuisine__iexact=parts[0]).exists():
        msg = f"More than one cuisine is called “{parts[0]}”: pick one from the list."
        raise CuisineNameError(msg)


def check_cuisine(text: str, *, owner: AbstractBaseUser) -> None:
    """Raise `CuisineNameError` if `resolve_cuisine` would refuse `text`; writes nothing."""
    if text.strip() and find_cuisine(text, owner=owner) is None:
        _check_cuisine(text, owner=owner)


def cuisine_path_map() -> dict[int, str]:
    """Every node's dotted path by its id, read in one query, private ones included."""
    return _path_map(Cuisine.objects.all())


def _path_map(nodes_query: QuerySet) -> dict[int, str]:
    nodes = {c.pk: c for c in nodes_query.only("pk", "cuisine", "parent")}
    paths = {}
    for pk, cuisine in nodes.items():
        names = [str(cuisine.cuisine)]
        parent_id = cuisine.parent_id
        while parent_id is not None and parent_id in nodes and len(names) <= MAX_CUISINE_DEPTH:
            names.insert(0, str(nodes[parent_id].cuisine))
            parent_id = nodes[parent_id].parent_id
        paths[pk] = PATH_SEPARATOR.join(names)
    return paths


def cuisine_paths(*, owner: AbstractBaseUser | None = None) -> list[str]:
    """The dotted path of every node `owner` sees, sorted: the editor's cuisine suggestions."""
    return sorted(set(_path_map(_visible_cuisines(owner)).values()), key=str.lower)


def _visible_units(owner: AbstractBaseUser | None) -> QuerySet:
    """The global units plus `owner`'s own, global first; only the global ones for None."""
    visible = Q(owner__isnull=True) if owner is None else Q(owner__isnull=True) | Q(owner=owner)
    return Unit.objects.filter(visible).order_by(F("owner").asc(nulls_first=True), "pk")


def _unit_text(text: str) -> str:
    """`text` as a unit name: spaces collapsed, a trailing full stop dropped."""
    return " ".join(text.split()).removesuffix(".").strip()


def find_unit(text: str, *, owner: AbstractBaseUser | None) -> Unit | None:
    """The unit `owner` sees as `text`, ignoring case, space and a trailing full stop.

    `Tbsp`, `tbsp.`, `tablespoons` and `tbs` are all `tbsp` (#67): the unit's
    name, its plural, an alias, or an alias's plural, in that order. `owner`
    sees the global units and their own (#154), a global unit winning, as for
    ingredients; None sees the global ones only. Never creates a unit. The
    vocabulary is a few dozen rows, so plurals are matched in Python.
    """
    name = _unit_text(text)
    if not name:
        return None
    lowered = name.lower()
    visible = _visible_units(owner)
    exact = visible.filter(name__iexact=name).first()
    if exact is not None:
        return exact
    plural = next((u for u in visible if u.plural.lower() == lowered), None)
    if plural is not None:
        return plural
    aliases = UnitAlias.objects.select_related("unit").filter(unit__owner__isnull=True)
    for alias in aliases.order_by("pk"):
        if lowered in {str(alias.alias_name).lower(), pluralise(str(alias.alias_name)).lower()}:
            return alias.unit
    return None


def resolve_unit(text: str, *, owner: AbstractBaseUser) -> Unit | None:
    """`find_unit`, or on a miss a new unit private to `owner`, with no dimension (#154).

    None for blank text, and for a size word or an amount phrase (`small`,
    `to taste`), which belong in the preparation or the note and never become
    a unit (`utils/unit_words.py`).
    """
    name = _unit_text(text)
    if not name or not_a_unit(name) is not None:
        return None
    found = find_unit(name, owner=owner)
    if found is not None:
        return found
    return Unit.objects.create(name=name, owner=owner)


def unit_names(*, owner: AbstractBaseUser) -> list[str]:
    """Unit names to suggest in `owner`'s editor, sorted ignoring case.

    The global units and `owner`'s own; a name they have in both is offered
    once, in the global spelling, which is the unit it resolves to.
    """
    names: dict[str, str] = {}
    for name in _visible_units(owner).values_list("name", flat=True):
        names.setdefault(name.lower(), name)
    return sorted(names.values(), key=lambda n: (n.lower(), n))
