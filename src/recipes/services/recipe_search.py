"""Search the signed-in user's recipes (#32).

A recipe matches when any typed term appears, at the start of a word, in the
fields being searched: by default its plain-text title and description, its
ingredients (or their substitutes), its tags and every level of its cuisine.
Results rank by how many terms matched, then by how many matched the title,
then newest first, which is also the order of the unsearched list. Excluded
terms (`-mushroom`) rule a recipe out wherever they appear. The cuisine filter
takes a node and everything below it; the tag filter a single tag.

Every term match is an `EXISTS` or a single-row join, so a recipe is never
repeated however many of its ingredients match. Pure ORM, no HTTP: the view
parses the request into a `RecipeSearch`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from operator import add, or_

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, QuerySet, Value, When
from django.db.models.functions import Lower

from recipes.models import Cuisine, IngredientInRecipe, Recipe, Tag
from recipes.models.cuisine import MAX_CUISINE_DEPTH
from recipes.utils.search_query import parse_query, term_variants, word_prefix_pattern

# Where to look: the box's "Search in" choices, the first being the default.
SEARCH_FIELDS = {
    "all": "Everywhere",
    "name": "Titles",
    "ingredient": "Ingredients",
}
DEFAULT_FIELD = "all"

# Recipe -> its cuisine node, the node's parent, and the grandparent.
_CUISINE_LEVELS = ["cuisine", "cuisine__parent", "cuisine__parent__parent"][:MAX_CUISINE_DEPTH]


@dataclass(frozen=True)
class RecipeSearch:
    """What to search for. The default instance is the plain, unsearched list."""

    query: str = ""
    field: str = DEFAULT_FIELD
    cuisine_id: int | None = None
    tag_id: int | None = None

    @property
    def is_active(self) -> bool:
        """True when anything narrows or reorders the list."""
        return bool(parse_query(self.query)) or bool(self.cuisine_id) or bool(self.tag_id)


def _ingredient_q(pattern: str, *, prefix: str = "") -> Q:
    return reduce(
        or_,
        (
            Q(**{f"{prefix}{fk}__ingredient_name__iregex": pattern})
            | Q(**{f"{prefix}{fk}__plural_name__iregex": pattern})
            for fk in ("ingredient", "substitute")
        ),
    )


def _term_q(term: str, *, field: str) -> tuple[Q, Q | None]:
    """(matches anywhere searched, matches the title or None if titles are not searched)."""
    patterns = [word_prefix_pattern(v) for v in term_variants(term)]
    title = reduce(or_, (Q(plain_name__iregex=p) for p in patterns))
    if field == "name":
        return title, title
    ingredients = Exists(
        IngredientInRecipe.objects.filter(ingredient_group__recipe=OuterRef("pk")).filter(
            reduce(or_, (_ingredient_q(p) for p in patterns))
        )
    )
    if field == "ingredient":
        return Q(ingredients), None
    tags = Exists(
        Tag.objects.filter(recipe=OuterRef("pk")).filter(
            reduce(or_, (Q(tag__iregex=p) for p in patterns))
        )
    )
    cuisine = reduce(
        or_, (Q(**{f"{level}__cuisine__iregex": p}) for level in _CUISINE_LEVELS for p in patterns)
    )
    description = reduce(or_, (Q(plain_description__iregex=p) for p in patterns))
    return title | description | Q(ingredients) | Q(tags) | cuisine, title


def _count(conditions: list[Q]) -> Case | Value:
    """How many of `conditions` a row meets, as an annotation."""
    if not conditions:
        return Value(0)
    return reduce(
        add,
        (
            Case(When(c, then=Value(1)), default=Value(0), output_field=IntegerField())
            for c in conditions
        ),
    )


def search_recipes(*, owner: AbstractBaseUser, search: RecipeSearch) -> QuerySet:
    """`owner`'s recipes matching `search`, best match first."""
    recipes = Recipe.objects.filter(owner=owner)
    if search.cuisine_id:
        recipes = recipes.filter(
            reduce(or_, (Q(**{f"{level}_id": search.cuisine_id}) for level in _CUISINE_LEVELS))
        )
    if search.tag_id:
        recipes = recipes.filter(tag__id=search.tag_id)
    parsed = parse_query(search.query)
    for term in parsed.excluded:
        anywhere, _title = _term_q(term, field=search.field)
        recipes = recipes.exclude(anywhere)
    if not parsed.terms:
        return recipes.order_by("-created_date", "-id")
    matches = [_term_q(term, field=search.field) for term in parsed.terms]
    return (
        recipes.annotate(
            matched=_count([anywhere for anywhere, _ in matches]),
            title_hits=_count([title for _, title in matches if title is not None]),
        )
        .filter(matched__gt=0)
        .order_by("-matched", "-title_hits", "-created_date", "-id")
    )


def matched_ingredients(*, recipes: Iterable[Recipe], search: RecipeSearch) -> dict[int, list[str]]:
    """Recipe id -> the ingredient names the search's terms found in it, A to Z.

    One query for the whole page, so the list can say "with aubergine" under a
    result whose title does not mention it.
    """
    terms = parse_query(search.query).terms
    if not terms or search.field == "name":
        return {}
    patterns = [word_prefix_pattern(v) for term in terms for v in term_variants(term)]
    rows = (
        IngredientInRecipe.objects.filter(ingredient_group__recipe__in=[r.pk for r in recipes])
        .filter(reduce(or_, (_ingredient_q(p) for p in patterns)))
        .values_list(
            "ingredient_group__recipe_id",
            "ingredient__ingredient_name",
            "ingredient__plural_name",
            "substitute__ingredient_name",
            "substitute__plural_name",
        )
    )
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    found: dict[int, set[str]] = {}
    for recipe_id, name, plural, sub_name, sub_plural in rows:
        for shown, forms in ((name, (name, plural)), (sub_name, (sub_name, sub_plural))):
            if shown and any(c.search(f) for c in compiled for f in forms if f):
                found.setdefault(recipe_id, set()).add(shown)
    return {rid: sorted(names, key=str.lower) for rid, names in found.items()}


def cuisine_choices(owner: AbstractBaseUser) -> list[Cuisine]:
    """Every cuisine node with one of `owner`'s recipes on it or below it, by path."""
    used = Cuisine.objects.filter(recipe__owner=owner).select_related("parent__parent").distinct()
    nodes: dict[int, Cuisine] = {}
    for node in used:
        for n in [*node.ancestors, node]:
            nodes.setdefault(n.pk, n)
    return sorted(nodes.values(), key=lambda c: c.path.lower())


def tag_choices(owner: AbstractBaseUser) -> list[Tag]:
    """Tags on `owner`'s recipes, global or private, A to Z."""
    return list(Tag.objects.filter(recipe__owner=owner).distinct().order_by(Lower("tag"), "tag"))
