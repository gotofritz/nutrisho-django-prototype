# Plan 008: Ingredient Aliases

## Status: Approved — ready to implement

Carried forward from [plan 007](../archive/2026-09-13-1551-eae5e1a-007-normalise-ingredients.md),
which shipped its Phases 1-7 as the clean-up tool. Phase 8 was always scoped to a
separate PR; this is that phase, unchanged apart from the renumbering.

Tracks [issue #14](https://github.com/gotofritz/nutrisho-django-prototype/issues/14).

## Goal

Recipes are scraped from many sources, so *input* has to tolerate variants that
differ by more than case (`eggplant` for `aubergine`). An `IngredientAlias` table
maps `alias_name → canonical Ingredient` and resolves at write time. Aliases are
input-only: they never become `Ingredient` rows and are never referenced by an
`IngredientInRecipe`, so storage and display always show the canonical British
form. Entering `eggplant` stores and shows `aubergine`, with no error.

Aliases are created three ways, in priority order: **(1) defined explicitly** in the
Miller tool (a first-class Alias action — declare `eggplant → aubergine` before it
is ever scraped); (2) recorded automatically when a **merge** collapses one
ingredient into another; (3) captured when a variant is **resolved manually** during
input. Explicit definition is the primary path; the others are conveniences.

This is **not** the old "variant survives as a row" model — there is no `canonical`
self-FK on `Ingredient`; aliases live in a separate lookup table and resolve at
write time only.

## Prerequisite (already shipped)

Plan 007 Phase 7.2 added
`UniqueConstraint(Lower("ingredient_name"), name="ingredient_name_ci_unique")`.
The alias collision rules below depend on it.

## TDD phases

Each cycle is **red → green → refactor**. Run `task qa` before the PR; keep
coverage ≥ 95%.

- **1** `IngredientAlias` model: `alias_name` (case-insensitive unique),
  `canonical = FK(Ingredient, on_delete=CASCADE, related_name="aliases")`. Migration.
  - Tests: create alias; duplicate `alias_name` (CI) rejected; an `alias_name`
    that collides (CI) with an existing `Ingredient.ingredient_name` rejected at
    validation (can't be both an alias and a canonical name); deleting the
    canonical cascades its aliases.
- **2** `resolve_ingredient(name) -> Ingredient` service, precedence:
  (1) CI alias hit → its canonical; (2) CI `Ingredient` hit → that row;
  (3) otherwise create a new canonical. Never raises on unknown input.
  - Tests: known alias → canonical (`eggplant` → `aubergine`); CI match to
    existing canonical; brand-new name creates canonical; returned/stored name is
    the canonical British form.
- **3** Route all *input* paths through `resolve_ingredient`, replacing raw
  `Ingredient.objects.get_or_create(ingredient_name=...)`:
  - `batch_load_yaml_recipes` importer
  - `IngredientInRecipeForm.save` / `resolve_pending_ingredient` (recipe-page add/edit)
  - ingredient-admin create/edit (the clean-up tool's Edit action)
  - Tests: importing a recipe naming `eggplant` yields an IIR pointing at
    `aubergine`; recipe-page add of `eggplant` shows `aubergine`; no duplicate
    `Ingredient` row created; no error surfaced.
- **4** Merge (the clean-up tool's Merge action) records aliases: merging victim → survivor creates
  `IngredientAlias(alias_name=victim.ingredient_name, canonical=survivor)` and
  **repoints the victim's existing aliases** to the survivor, inside the same
  transaction, before deleting the victim.
  - Tests: post-merge alias row exists; `resolve_ingredient("eggplant")` →
    `aubergine`; victim's prior aliases now point at survivor; no orphaned aliases.
- **5** First-class **Alias** action in the Miller tool (4th col-1 button,
  alongside Edit/Delete/Merge; enabled when exactly 1 canonical is selected).
  Workspace panel: list the selected ingredient's existing aliases, add new
  alias name(s), remove aliases. This is the **explicit mapping** path — declare
  `eggplant → aubergine` directly, before anything is scraped.
  - Tests: panel lists current aliases; add alias persists and resolves
    (`resolve_ingredient("eggplant")` → selected canonical); remove deletes the
    mapping; adding a name that collides (CI) with an existing alias or canonical
    is rejected (reuses phase 1 validation); guard requires exactly 1 selected.
- **6** Convergence — adding an alias whose name **is already an `Ingredient`**
  (i.e. the variant exists as its own row, possibly used by recipes) is merge
  semantics, not a bare insert. Detect this in the Alias action and route through
  the existing `merge_ingredients` service (repoint IIR `ingredient`+`substitute`,
  delete the row, record the alias) so no data is stranded.
  - Tests: defining `eggplant → aubergine` when an `eggplant` ingredient row
    exists repoints its recipes to `aubergine`, deletes the row, and leaves the
    alias; defining an alias for a name with no existing row is a plain insert
    (no merge).
- **7** Manual-resolution capture (input side): when an importer/input hits a
  name that resolves to nothing and the owner picks a canonical for it, store the
  chosen mapping as an alias via the same service. (Lightweight; reuses phases 2 and 5.)
  - Tests: resolving an unknown variant to a canonical creates the alias; the next
    input of that variant resolves without prompting.
- **8** Docs: update `docs/initial-context.md` (alias-resolution layer, the
  "resolve on input, store/display canonical" rule, the three creation paths) and
  `README.md`.

## Out of scope

- True fuzzy ranking (trigram) — `icontains` only, as in plan 007.
- De-duplicating `IngredientInRecipe` rows after a merge.
- Staff/superuser gating (login-only for the prototype).
- Bulk undo / audit log.
