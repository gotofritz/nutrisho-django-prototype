"""Query and mutation services for the shared-Ingredient clean-up tool.

Pure ORM helpers with no HTTP concerns, so the HTMX views in
`recipes/views/ingredient_admin.py` stay thin.
"""

from collections.abc import Iterable
from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Lower

from recipes.models import Ingredient, IngredientInRecipe, Recipe


class IngredientInUseError(Exception):
    """Raised when a delete would strand recipes that still reference an ingredient."""


def search_ingredients(
    query: str, *, unused_only: bool = False, plurals_only: bool = False
) -> QuerySet:
    """`Ingredient` rows whose name contains `query`, case-insensitively.

    Ordered case-insensitively so spelling variants of one ingredient
    (`Onion` / `onion`) sort next to each other — the whole point of the
    clean-up tool. Ties break on the raw name to keep the order deterministic;
    only databases predating `ingredient_name_ci_unique` can still tie.

    `unused_only` narrows the list to orphans: rows no `IngredientInRecipe`
    references, as an ingredient or as a substitute. Either reference PROTECTs
    the row, so anything excluded here cannot be deleted outright anyway. Not
    owner-scoped — ingredients are shared, so another owner's recipe still
    counts as a use. Orphans accumulate from renames (which get_or_create leaves
    behind), from deleting the last row that used one, and from imports.

    `plurals_only` narrows the list to rows that are one half of a
    singular/plural pair (`onion` alongside `onions`). A plural is a display
    form, not a second ingredient, so such a pair is bad data: this is how the
    owner finds them and merges the plural into the singular. Composes with the
    other two filters.
    """
    matches = Ingredient.objects.all()
    if query:
        matches = matches.filter(ingredient_name__icontains=query)
    if plurals_only:
        # The plural of a name is computed in Python (rule plus override), so the
        # pairs cannot be expressed as a lookup; narrow by their ids instead.
        matches = matches.filter(
            pk__in={row.pk for group in find_plural_duplicates() for row in group}
        )
    if unused_only:
        matches = matches.exclude(
            Q(pk__in=IngredientInRecipe.objects.values("ingredient"))
            | Q(
                pk__in=IngredientInRecipe.objects.filter(substitute__isnull=False).values(
                    "substitute"
                )
            )
        )
    return matches.order_by(Lower("ingredient_name"), "ingredient_name")


def selected_ingredients(ingredient_ids: Iterable[int]) -> QuerySet:
    """The named `Ingredient` rows, ordered exactly as column 2 lists them.

    Unknown ids are ignored, so a stale selection degrades to a shorter list
    rather than an error.
    """
    return Ingredient.objects.filter(pk__in=list(ingredient_ids)).order_by(
        Lower("ingredient_name"), "ingredient_name"
    )


def recipes_referencing_ingredients(ingredient_ids: Iterable[int]) -> QuerySet:
    """Every `Recipe`, any owner, referencing ANY of `ingredient_ids`.

    A reference counts whether the ingredient is used directly or as a
    substitute: merge and delete repoint both FKs, so either makes the recipe
    something a clean-up would touch.

    Deliberately not owner-scoped — `Ingredient` rows are shared, so a delete
    has to account for recipes the current user cannot see.
    """
    ids = list(ingredient_ids)
    if not ids:
        return Recipe.objects.none()
    return (
        Recipe.objects.filter(
            Q(ingredients_group__ingredient__ingredient__in=ids)
            | Q(ingredients_group__ingredient__substitute__in=ids)
        )
        .distinct()
        .order_by(Lower("recipe_name"), "recipe_name")
    )


def recipes_for_ingredients(*, ingredient_ids: Iterable[int], owner: AbstractBaseUser) -> QuerySet:
    """Owner's slice of `recipes_referencing_ingredients` (Decision 4: union).

    Column 3 stays owner-scoped even though the ingredients themselves are not.
    """
    return recipes_referencing_ingredients(ingredient_ids).filter(owner=owner)


@transaction.atomic
def delete_ingredients(*, ingredient_ids: Iterable[int], replacement_id: int | None = None) -> int:
    """Delete ingredients, repointing every recipe reference first.

    `IngredientInRecipe.ingredient` and `.substitute` are both PROTECTed, so a
    referenced ingredient can only go once both FKs point at `replacement_id`.
    Repointing an FK leaves `index_in_sequence` alone, so recipe ordering
    survives untouched.

    The replacement is never itself deleted, even when it was part of the
    selection. Raises `IngredientInUseError` when recipes still reference a
    victim and no usable replacement was given; nothing is written in that case.

    Returns the number of `Ingredient` rows deleted.
    """
    victim_ids = [i for i in dict.fromkeys(ingredient_ids) if i != replacement_id]
    if not victim_ids:
        return 0
    references = IngredientInRecipe.objects.filter(
        Q(ingredient__in=victim_ids) | Q(substitute__in=victim_ids)
    )
    if references.exists():
        replacement = (
            Ingredient.objects.filter(pk=replacement_id).first()
            if replacement_id is not None
            else None
        )
        if replacement is None:
            raise IngredientInUseError(
                "Recipes still use these ingredients — pick a replacement first."
            )
        # Lock the referencing rows before rewriting them, matching
        # recipe_ingredient_reassign (a no-op on SQLite, which serializes anyway).
        list(references.select_for_update().values("pk"))
        IngredientInRecipe.objects.filter(ingredient__in=victim_ids).update(ingredient=replacement)
        IngredientInRecipe.objects.filter(substitute__in=victim_ids).update(substitute=replacement)
    _, per_model = Ingredient.objects.filter(pk__in=victim_ids).delete()
    return per_model.get("recipes.Ingredient", 0)


@transaction.atomic
def merge_ingredients(*, survivor_id: int, victim_ids: Iterable[int]) -> int:
    """Collapse `victim_ids` into `survivor_id`, carrying their recipes across.

    Repoints both `IngredientInRecipe.ingredient` and `.substitute` onto the
    survivor, then deletes the victims, in one transaction. The survivor row is
    left exactly as it is — renaming it is a separate Edit action (Decision 6),
    and the survivor is never deleted even if it appears in `victim_ids`.

    A recipe that already used the survivor *and* a victim keeps both rows: no
    constraint forbids listing one ingredient twice in a group, and
    de-duplicating is out of scope (Plan 007, 6.3).

    Raises `ObjectDoesNotExist` for an unknown survivor. Re-running once the
    victims are gone is a no-op.

    Returns the number of `Ingredient` rows merged away.
    """
    if not Ingredient.objects.filter(pk=survivor_id).exists():
        raise ObjectDoesNotExist(f"No Ingredient with id {survivor_id}")
    return delete_ingredients(ingredient_ids=victim_ids, replacement_id=survivor_id)


def find_ingredient_duplicates() -> list[list[Ingredient]]:
    """Ingredient rows whose names differ only by case, grouped.

    Each group holds at least two rows, ordered by raw name; groups are ordered
    case-insensitively, as column 2 lists them. Exists for databases created
    before the `ingredient_name_ci_unique` constraint: run the command, merge
    what it reports with the clean-up tool, then migrate.
    """
    clashing_names = (
        Ingredient.objects.values(lowered=Lower("ingredient_name"))
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .order_by("lowered")
        .values_list("lowered", flat=True)
    )
    return [
        list(Ingredient.objects.filter(ingredient_name__iexact=name).order_by("ingredient_name"))
        for name in clashing_names
    ]


def find_plural_duplicates() -> list[list[Ingredient]]:
    """Rows paired with the row that spells out their plural, singular first.

    The third variant class (issue #24), alongside case (`Onion`/`onion`) and
    alias (`eggplant`/`aubergine`). A plural is the display form of one
    ingredient at a quantity other than 1, so an `onions` row sitting next to
    `onion` is bad data, not a variant to keep: merge it into the singular and
    let `display_ingredient_name` add the "s".

    Matching is case-insensitive and goes through `Ingredient.plural`, so both
    the rule (`tomato` → `tomatoes`) and a `plural_name` override
    (`avocado` → `avocados`) find their partner. Invariant rows — anything whose
    plural equals its own name — pair with nothing. Groups are ordered
    case-insensitively, as column 2 lists them.
    """
    rows = list(Ingredient.objects.all())
    by_name = {row.ingredient_name.lower(): row for row in rows}
    groups = [
        [row, by_name[row.plural.lower()]]
        for row in rows
        if row.plural.lower() != row.ingredient_name.lower() and row.plural.lower() in by_name
    ]
    return sorted(groups, key=lambda group: cast(str, group[0].ingredient_name).lower())
