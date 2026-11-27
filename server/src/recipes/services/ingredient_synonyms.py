"""Common synonyms as aliases of the ingredient the lists hold (#203).

The alias mechanism (plan 008) resolves `eggplant` to `aubergine` once staff
add the alias; this is a curated list of the synonyms a clipped recipe
commonly brings, mostly American names for British ones, so they need not be
added one by one. Each group starts with the British name, the house
canonical; the first name of a group that is a global ingredient becomes the
canonical, and the rest of the group its aliases, through `add_alias`, which
folds in any row already holding that name. A name already aliased to another
ingredient is left alone: staff chose that.
"""

from dataclasses import dataclass
from typing import cast

from recipes.models import Ingredient, IngredientAlias
from recipes.services.ingredient_admin import add_alias
from recipes.services.ingredient_journal import Journal

SYNONYMS: tuple[tuple[str, ...], ...] = (
    ("aubergine", "eggplant", "brinjal"),
    ("courgette", "zucchini"),
    ("coriander", "cilantro"),
    ("rocket", "arugula"),
    ("spring onion", "scallion", "green onion"),
    ("soya sauce", "soy sauce"),
    ("soya bean", "soybean", "soy bean"),
    ("chickpea", "garbanzo bean", "garbanzo"),
    ("swede", "rutabaga"),
    ("beetroot", "beet"),
    ("mangetout", "snow pea"),
    ("broad bean", "fava bean"),
    ("haricot bean", "navy bean"),
    ("black-eyed bean", "black-eyed pea"),
    ("pak choi", "bok choy"),
    ("celeriac", "celery root"),
    ("cos lettuce", "romaine lettuce", "romaine"),
    ("plain flour", "all-purpose flour", "all purpose flour"),
    ("self-raising flour", "self-rising flour"),
    ("wholemeal flour", "whole wheat flour", "whole-wheat flour"),
    ("strong white flour", "bread flour"),
    ("cornflour", "cornstarch"),
    ("caster sugar", "superfine sugar"),
    ("icing sugar", "powdered sugar", "confectioners' sugar", "confectioners sugar"),
    ("bicarbonate of soda", "baking soda"),
    ("double cream", "heavy cream"),
    ("single cream", "light cream"),
    ("minced beef", "ground beef"),
    ("minced pork", "ground pork"),
    ("chilli", "chili", "chile"),
    ("chilli flakes", "red pepper flakes", "chili flakes"),
    ("prawn", "shrimp"),
    ("tomato purée", "tomato paste"),
    ("stock cube", "bouillon cube"),
    ("sultana", "golden raisin"),
    ("glacé cherry", "candied cherry"),
    ("filo pastry", "phyllo dough", "phyllo", "filo"),
    ("yoghurt", "yogurt"),
    ("rapeseed oil", "canola oil"),
    ("groundnut oil", "peanut oil"),
)


@dataclass(frozen=True)
class SynonymPlanEntry:
    """One alias to add: the name, what it will mean, and the rows it folds in."""

    alias: str
    canonical: Ingredient
    merges: int
    clash: str = ""


def _canonical(group: tuple[str, ...]) -> Ingredient | None:
    """The group's first name that is a global ingredient, ignoring case."""
    for name in group:
        found = Ingredient.objects.filter(owner__isnull=True, ingredient_name__iexact=name).first()
        if found is not None:
            return found
    return None


def _entry(name: str, canonical: Ingredient) -> SynonymPlanEntry | None:
    """What adding `name` to `canonical` would do; None when it already resolves."""
    lowered = name.lower()
    if lowered in {cast(str, canonical.ingredient_name).lower(), canonical.plural.lower()}:
        return None
    existing = IngredientAlias.objects.filter(alias_name__iexact=name).first()
    if existing is not None:
        if existing.canonical_id == canonical.pk:
            return None
        return SynonymPlanEntry(
            alias=name,
            canonical=canonical,
            merges=0,
            clash=f"already an alias of “{existing.canonical}”",
        )
    merges = Ingredient.objects.filter(ingredient_name__iexact=name).count()
    return SynonymPlanEntry(alias=name, canonical=canonical, merges=merges)


def plan_synonym_aliases(
    *, synonyms: tuple[tuple[str, ...], ...] = SYNONYMS
) -> list[SynonymPlanEntry]:
    """Every alias the list would add, in its order; clashes included, to report."""
    plan: list[SynonymPlanEntry] = []
    for group in synonyms:
        canonical = _canonical(group)
        if canonical is None:
            continue
        for name in group:
            entry = _entry(name, canonical)
            if entry is not None:
                plan.append(entry)
    return plan


def apply_synonym_aliases(plan: list[SynonymPlanEntry], *, journal: Journal) -> int:
    """Add each alias the plan holds, clashes left out; returns how many."""
    todo = [entry for entry in plan if not entry.clash]
    if todo:
        journal.describe(
            f"Added {len(todo)} {'synonym' if len(todo) == 1 else 'synonyms'} as aliases"
        )
    for entry in todo:
        add_alias(canonical_id=entry.canonical.pk, alias_name=entry.alias, journal=journal)
    return len(todo)
