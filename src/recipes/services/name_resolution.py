"""Resolve names typed into the recipe editor to `Ingredient`, `Tag` and `Cuisine` rows.

Names are unique ignoring case, so `Onion` typed on a phone that
auto-capitalises is the stored `onion`, not a second row. Lookups are
case-insensitive and keep the stored spelling; a miss creates an ingredient or
tag as typed, but never a cuisine, which only staff add.
Ingredients and tags are scoped to the recipe's owner: the global list plus
their own private rows (plan 011).
Every editor path goes through here rather than calling `get_or_create` on the
raw name, which matched case-sensitively and then hit the unique index (#34).
"""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F, Q, QuerySet

from recipes.models import Cuisine, Ingredient, Tag
from recipes.models.cuisine import MAX_CUISINE_DEPTH, PATH_SEPARATOR


def _visible_ingredients(owner: AbstractBaseUser) -> QuerySet:
    """The global list plus `owner`'s private rows; never anyone else's."""
    return Ingredient.objects.filter(Q(owner__isnull=True) | Q(owner=owner))


def find_ingredient(name: str, *, owner: AbstractBaseUser) -> Ingredient | None:
    """The ingredient `owner` sees as `name`, ignoring case and surrounding space.

    A global row wins over the owner's private row of the same name: once staff
    have made a name global, that is the ingredient everyone means.
    """
    return (
        _visible_ingredients(owner)
        .filter(ingredient_name__iexact=name.strip())
        .order_by(F("owner").asc(nulls_first=True))
        .first()
    )


def resolve_ingredient(name: str, *, owner: AbstractBaseUser) -> Ingredient:
    """`find_ingredient`, or on a miss a new row private to `owner`, as typed.

    Private until staff promote it (plan 011): an unknown name is one user's
    vocabulary, typos included, and must not appear in anyone else's editor.
    """
    found = find_ingredient(name, owner=owner)
    if found is not None:
        return found
    return Ingredient.objects.create(ingredient_name=name.strip(), owner=owner)


def ingredient_names_for(owner: AbstractBaseUser) -> list[str]:
    """Names to suggest in `owner`'s recipe editor: global plus their own, sorted."""
    names = _visible_ingredients(owner).values_list("ingredient_name", flat=True)
    return sorted(set(names), key=lambda n: (n.lower(), n))


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
