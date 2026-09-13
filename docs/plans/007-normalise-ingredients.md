# Plan 007: Normalise Ingredients

## Status: Draft

Tracks [issue #14](https://github.com/gotofritz/nutrisho-django-prototype/issues/14).

## Goal

Give the owner a tool to clean up the shared `Ingredient` table: find duplicate /
variant ingredients (plurals, alternate spellings, alternate names) and **edit**,
**delete**, or **merge** them, seeing which recipes are affected before committing.

The tool is a custom **Miller-columns** UI (cascading columns), HTMX-driven, reusing
the existing inline-edit + reassign patterns. No new frontend framework.

```
┌──────────────┬─────────────────┬──────────────────┬─────────────────┐
│ 1 actions    │ 2 ingredients   │ 3 recipes        │ 4 preview       │
│              │   [x] aubergine │  Moussaka        │  Moussaka       │
│ ← back       │   [ ] eggplant  │  Ratatouille     │  Serves 4       │
│ [search…]    │   [x] onion     │                  │  • aubergine …  │
│              │   [ ] onions    │                  │  1. Slice …     │
│ Edit         │  2 found /      │  2 matches /     │                 │
│ Delete       │  2 selected     │  2 selected      │                 │
│ Merge        │  (≤38ch, wrap)  │  (≤62ch)         │  (no nav)       │
└──────────────┴─────────────────┴──────────────────┴─────────────────┘
```

Clicking an action collapses columns 2–4 into a single full-width **workspace**
panel (edit forms / delete confirm / merge chooser). The clicked button becomes
**Cancel**, which restores the previous 3-column state. Completing an action
updates the columns to reflect the new DB state.

---

## Decisions (confirmed 2026-06-14)

All resolved to the recommended option (in **bold**). Reopen on the PR to change
before the relevant phase.

1. **Schema for plurals / alt-spellings / alt-names** *(revised 2026-06-15)*.
   Two stages:
   - **Start — merge-based, no alias table.** Treat variants as duplicates to be
     merged away. British spelling is canonical (per the issue: *"I am ok if we
     decide to only stick to British"*). Lock it in with a **case-insensitive
     uniqueness** constraint (Phase 7). The Miller tool *is* the normalisation
     mechanism. Phases 1–7 deliver this.
   - **Later — alias-resolution layer (Phase 8).** Recipes are scraped from many
     sources, so input must tolerate variants. An **`IngredientAlias`** table maps
     `alias_name → canonical Ingredient`. On *input* (importer, recipe-page add,
     admin create) a name is resolved through aliases to its canonical row before
     `get_or_create`. Aliases are **input-only**: they never become `Ingredient`
     rows and are never referenced by an `IngredientInRecipe`, so storage and
     display always show the canonical British form. Entering `eggplant` stores
     and shows `aubergine`, with no error. Aliases are created three ways, in
     priority order: **(1) defined explicitly** in the Miller tool (a first-class
     Alias action — declare `eggplant → aubergine` up front, before it is ever
     scraped); (2) recorded automatically when a **merge** collapses one
     ingredient into another; (3) captured when a variant is **resolved manually**
     during input. Explicit definition is the primary path; the others are
     conveniences.

   This is **not** the old "variant survives as a row" model — there is no
   `canonical` self-FK on `Ingredient`; aliases live in a separate lookup table
   and resolve at write time only. The Miller UI (Phases 1–6) is unaffected.

2. **Access control.** Recommended: **login-only** (`htmx_login_required`, as the
   rest of the app), single-user prototype. Staff/superuser-gating is noted as a
   future hardening step (the tool does bulk deletes).

3. **"Back" target (col 1).** Recommended: link to Django `/admin/`. Trivial to
   repoint to `/recipes/` if preferred.

4. **"Recipes that match the selected ingredients" semantics.** Recommended:
   **ANY-of (union)** — recipes containing *any* selected ingredient — since the
   point is to inspect everything a clean-up would touch. (Intersection is the
   alternative; easy to switch.)

5. **Fuzzy search depth.** Recommended: **case-insensitive substring**
   (`icontains`) for v1. SQLite has no trigram extension; true fuzzy ranking is a
   future step.

---

## Constraints to respect (from the codebase)

- `IngredientInRecipe.ingredient` **and** `.substitute` are both
  `on_delete=PROTECT`. **An ingredient cannot be deleted while any IIR references
  it as either ingredient or substitute.** Merge and delete-with-replacement must
  repoint *both* FKs before deleting.
- `Ingredient.ingredient_name` is `unique` (max 64). Rename validation must not
  collide.
- Recipes are owner-scoped (`owner=request.user`); ingredients are global. Preview
  (col 4) stays owner-scoped.
- Reuse `recipes/utils/sequencing.py` for any `index_in_sequence` writes; do not
  reimplement index arithmetic. Repointing the `ingredient` FK on an IIR does
  **not** touch `index_in_sequence`, so merges/deletes leave ordering intact.
- Multi-row mutations go inside `transaction.atomic` (see `recipe_ingredient_reassign`
  as the reference implementation).

---

## Architecture

New, self-contained subsystem under the `recipes` app — separate from the
per-recipe inline editor and from Django admin:

```
src/recipes/
  services/
    __init__.py
    ingredient_admin.py     # pure query + mutation functions (no HTTP)
  forms/
    ingredient_admin_forms.py  # IngredientForm, DeleteIngredientsForm, MergeIngredientsForm
  views/
    ingredient_admin.py     # HTMX views returning partials
  templates/recipes/ingredient_admin/
    manager.html            # full-page 4-column shell
    _columns.html           # cols 2–4 (restored on cancel/back)
    _ingredient_list.html   # col 2 (checkbox list + header counts)
    _recipe_matches.html    # col 3 (recipe list + header counts)
    _recipe_preview.html    # col 4 (read-only recipe render, no nav)
    _edit_panels.html       # workspace: one edit form per selected ingredient
    _ingredient_panel.html  # single edit form (save target)
    _delete_confirm.html    # workspace: confirm + optional replacement picker
    _merge_chooser.html     # workspace: selected list with survivor radios
tests/recipes/
  test_ingredient_admin_services.py
  test_ingredient_admin_views.py
  test_ingredient_admin_forms.py
```

Selection lives in the request (checkbox `name="ingredient_ids"`), echoed back into
re-rendered partials so checkboxes stay checked and counts stay correct — no
client-side store, matching the existing reassign flow. Action panels carry the
selected ids as hidden inputs so Cancel/Save can restore state.

### URL scheme (added to `recipes/urls.py`, all `_lr`-wrapped)

```
/recipes/ingredients/manage/                 GET  — 4-column shell
/recipes/ingredients/manage/search/          GET  ?q=&ingredient_ids=  → col 2 list
/recipes/ingredients/manage/recipes/         GET  ?ingredient_ids=     → col 3 list
/recipes/ingredients/manage/preview/<id>/    GET  → col 4 recipe preview
/recipes/ingredients/manage/cancel/          GET  ?q=&ingredient_ids=  → restore cols 2–4
# actions (GET = show workspace panel, POST = perform)
/recipes/ingredients/manage/edit/            GET  ?ingredient_ids=     → edit panels
/recipes/ingredients/manage/<id>/save/       POST → save one ingredient, return its panel
/recipes/ingredients/manage/delete/          GET  ?ingredient_ids=     → confirm (+replacement)
/recipes/ingredients/manage/delete/          POST → perform delete (optional replacement_id)
/recipes/ingredients/manage/merge/           GET  ?ingredient_ids=     → survivor chooser
/recipes/ingredients/manage/merge/           POST → perform merge (survivor_id + ids)
```

> `manage/` prefix keeps these clear of the existing
> `/<recipe_id>/ingredients/...` inline-edit routes.

---

## TDD phases

Each cycle is **red → green → refactor**. Backend services are tested first and in
isolation, so the HTMX views stay thin. Run `task qa` before the PR; keep coverage
≥ 95%.

### Phase 1 — Read-only services + shell

- **1.1** `search_ingredients(query: str) -> QuerySet[Ingredient]`
  - Tests: empty query → all, alphabetical; `icontains` case-insensitive
    (`"ONI"` matches `onion`); ordering stable.
- **1.2** `recipes_for_ingredients(ingredient_ids: Iterable[int], owner) -> QuerySet[Recipe]`
  - Tests: returns recipes (ANY-of, `distinct()`) owner-scoped; two ingredients
    union; empty ids → empty; ingredient used twice → recipe listed once.
- **1.3** `manager` view + URL → renders `manager.html` (login required).
  - Tests: 200 for auth user; redirect/login for anon; contains the four column
    containers, a back link, a search input, and **disabled** Edit/Delete/Merge
    buttons.
- **1.4** `search` view → `_ingredient_list.html` (col 2).
  - Tests: lists all alphabetically with a checkbox per row; `?q=` filters;
    fixed header renders `"N found / 0 selected"`; column has the
    width/scroll/wrap class (≤38ch). 404-free on empty.

### Phase 2 — Recipe matches + preview

- **2.1** `recipes` view → `_recipe_matches.html` (col 3).
  - Tests: lists matching recipes, **no** checkboxes; header
    `"N matches / M selected"`; empty selection → empty/placeholder; width class
    (≤62ch); each row links (hx-get) to its preview.
- **2.2** `preview` view → `_recipe_preview.html` (col 4), new read-only render.
  - Tests: shows recipe name, ingredient groups/lines, steps; contains **no**
    nav and **no** edit controls (no `hx-get .../edit/`); 404 for a recipe owned
    by someone else.

### Phase 3 — Selection plumbing + action enablement + cancel

- **3.1** Selection round-trips: col 2 re-render keeps boxes checked from
  `ingredient_ids`; header counts update; selecting refreshes col 3
  (`hx-trigger` on change).
  - Tests: posting/getting with `ingredient_ids` echoes `checked`; col 2 header
    shows correct "selected"; col 3 reflects the same selection.
- **3.2** Server-side action guards: edit needs ≥1, delete needs ≥1, merge needs
  ≥2 selected. Buttons render `disabled` client-side; endpoints reject otherwise.
  - Tests: GET edit/delete with 0 ids → 422 (or guarded message); GET merge with
    <2 ids → 422.
- **3.3** `cancel` view restores cols 2–4 (`_columns.html`) with `q` + selection
  intact.
  - Tests: cancel returns the 3-column partial; selection preserved; counts
    correct.

### Phase 4 — Edit action

- **4.1** `IngredientForm` (ModelForm: `ingredient_name`, `family`,
  `dietary_constraint`).
  - Tests: valid save; rename to an existing name rejected (respect `unique`,
    case-insensitive); whitespace stripped; choices validated.
- **4.2** `edit` view → `_edit_panels.html`: one `_ingredient_panel.html` per
  selected ingredient, each its own `<form>` + Save button posting to
  `<id>/save/`.
  - Tests: N selected → N panels, each pre-filled; hidden selection carried; the
    clicked action shows a **Cancel** affordance.
- **4.3** `save` view (POST) → persists one ingredient, returns its updated panel
  (`outerHTML` swap); invalid → panel with errors.
  - Tests: rename persists and col 2 row reflects new name; independent saves
    don't disturb sibling panels; 404 for unknown id; invalid name → errors, no
    write.

### Phase 5 — Delete action

- **5.1** `delete` view (GET) → `_delete_confirm.html`. If any selected ingredient
  is referenced by a recipe (as ingredient **or** substitute), include the count
  of affected recipes and a **replacement** picker (datalist/select of other
  ingredients).
  - Tests: all-unused → plain confirm, no picker; some used → shows affected
    count + replacement picker.
- **5.2** `delete_ingredients(ids, replacement_id=None)` service + POST, **unused**
  case → deletes; col 2 refreshes without them.
  - Tests: unused ingredient removed; col 2 no longer lists it; counts updated.
- **5.3** Delete **used** WITH `replacement_id` → repoint `IIR.ingredient` and
  `IIR.substitute` from victims to replacement (transactional), then delete.
  - Tests: affected recipes now reference replacement; `substitute` refs also
    repointed; victims deleted; `index_in_sequence` untouched; PROTECT no longer
    fires.
- **5.4** Delete **used** WITHOUT replacement → blocked.
  - Tests: returns 422 with a clear message; nothing deleted.

### Phase 6 — Merge action

- **6.1** `merge` view (GET, ≥2 selected) → `_merge_chooser.html`: the selected
  ingredients, each with a radio to pick the **survivor** (first selected default).
  - Tests: radios rendered for each; <2 selected guarded (Phase 3.2).
- **6.2** `merge_ingredients(survivor_id, victim_ids)` service + POST: repoint
  `IIR.ingredient` and `IIR.substitute` from victims to survivor (transactional),
  delete victims.
  - Tests: recipes using a victim now use survivor; survivor row unchanged;
    victims deleted; `substitute` refs repointed; col 2 collapses the merged rows
    into one; idempotent re-run is a no-op.
- **6.3** Edge — a recipe already containing the survivor *and* a victim: merge is
  allowed to leave two IIR rows of the same ingredient (no unique constraint
  forbids it). Document the behaviour with a test; de-duplication is out of scope.

### Phase 7 — Lock in normalisation + polish + docs

- **7.1** `find_ingredient_duplicates()` service + `find_ingredient_duplicates`
  management command (lists case-insensitive name clashes so they can be merged
  with the new tool).
  - Tests: detects `Onion`/`onion`; clean DB → empty.
- **7.2** Add case-insensitive uniqueness:
  `UniqueConstraint(Lower('ingredient_name'), name='ingredient_name_ci_unique')`
  + migration. (Run **after** the tool exists to clear existing clashes.)
  - Tests: creating `Onion` then `onion` raises `IntegrityError`; migration applies
    cleanly on a de-duplicated DB.
- **7.3** CSS (Tailwind): column widths (≤38ch col 2, ≤62ch col 3), vertical-only
  scroll, text wrap, collapsed full-width workspace. Build via `task css`.
  - Manual check + a thin assertion that the width/scroll classes are present.
- **7.4** Docs: update `docs/initial-context.md` (new ingredient-admin subsystem,
  services layer, merge/delete repointing rule, CI-unique constraint) and
  `README.md` (how to reach the clean-up tool). Per AGENTS.md, archive this plan
  in the same PR (`docs/archive/YYYY-MM-DD-HHMM-<shortsha>-007-normalise-ingredients.md`).
- **7.5** `task qa` green; coverage ≥ 95%.

### Phase 8 — Alias-resolution layer (later; input → canonical British)

Ships after Phases 1–7 are merged. Lets scraped/typed variants resolve to the
canonical British ingredient at write time; storage and display stay canonical.

- **8.1** `IngredientAlias` model: `alias_name` (case-insensitive unique),
  `canonical = FK(Ingredient, on_delete=CASCADE, related_name="aliases")`. Migration.
  - Tests: create alias; duplicate `alias_name` (CI) rejected; an `alias_name`
    that collides (CI) with an existing `Ingredient.ingredient_name` rejected at
    validation (can't be both an alias and a canonical name); deleting the
    canonical cascades its aliases.
- **8.2** `resolve_ingredient(name) -> Ingredient` service, precedence:
  (1) CI alias hit → its canonical; (2) CI `Ingredient` hit → that row;
  (3) otherwise create a new canonical. Never raises on unknown input.
  - Tests: known alias → canonical (`eggplant` → `aubergine`); CI match to
    existing canonical; brand-new name creates canonical; returned/stored name is
    the canonical British form.
- **8.3** Route all *input* paths through `resolve_ingredient`, replacing raw
  `Ingredient.objects.get_or_create(ingredient_name=...)`:
  - `batch_load_yaml_recipes` importer
  - `IngredientInRecipeForm.save` / `resolve_pending_ingredient` (recipe-page add/edit)
  - ingredient-admin create/edit (Phase 4)
  - Tests: importing a recipe naming `eggplant` yields an IIR pointing at
    `aubergine`; recipe-page add of `eggplant` shows `aubergine`; no duplicate
    `Ingredient` row created; no error surfaced.
- **8.4** Merge (Phase 6) records aliases: merging victim → survivor creates
  `IngredientAlias(alias_name=victim.ingredient_name, canonical=survivor)` and
  **repoints the victim's existing aliases** to the survivor, inside the same
  transaction, before deleting the victim.
  - Tests: post-merge alias row exists; `resolve_ingredient("eggplant")` →
    `aubergine`; victim's prior aliases now point at survivor; no orphaned aliases.
- **8.5** First-class **Alias** action in the Miller tool (4th col-1 button,
  alongside Edit/Delete/Merge; enabled when exactly 1 canonical is selected).
  Workspace panel: list the selected ingredient's existing aliases, add new
  alias name(s), remove aliases. This is the **explicit mapping** path — declare
  `eggplant → aubergine` directly, before anything is scraped.
  - Tests: panel lists current aliases; add alias persists and resolves
    (`resolve_ingredient("eggplant")` → selected canonical); remove deletes the
    mapping; adding a name that collides (CI) with an existing alias or canonical
    is rejected (reuses 8.1 validation); guard requires exactly 1 selected.
- **8.6** Convergence — adding an alias whose name **is already an `Ingredient`**
  (i.e. the variant exists as its own row, possibly used by recipes) is merge
  semantics, not a bare insert. Detect this in the Alias action and route through
  the Phase 6 `merge_ingredients` service (repoint IIR `ingredient`+`substitute`,
  delete the row, record the alias) so no data is stranded.
  - Tests: defining `eggplant → aubergine` when an `eggplant` ingredient row
    exists repoints its recipes to `aubergine`, deletes the row, and leaves the
    alias; defining an alias for a name with no existing row is a plain insert
    (no merge).
- **8.7** Manual-resolution capture (input side): when an importer/input hits a
  name that resolves to nothing and the owner picks a canonical for it, store the
  chosen mapping as an alias via the same service. (Lightweight; reuses 8.2/8.5.)
  - Tests: resolving an unknown variant to a canonical creates the alias; the next
    input of that variant resolves without prompting.
- **8.8** Docs: update `docs/initial-context.md` (alias-resolution layer, the
  "resolve on input, store/display canonical" rule, the three creation paths) and
  `README.md`.

> Phase 7's case-insensitive uniqueness on `Ingredient.ingredient_name` is a
> prerequisite — alias collision rules depend on it.

---

## Out of scope (note for reviewers)

- Alias resolution ships in Phase 8 (later), not in the Phases 1–7 PR. A
  `canonical` self-FK on `Ingredient` is explicitly **not** used — aliases live in
  a separate `IngredientAlias` lookup table.
- True fuzzy ranking (trigram) — `icontains` only for now.
- De-duplicating IIR rows after a merge (6.3).
- Staff/superuser gating (login-only for the prototype).
- Bulk undo / audit log of merges and deletes.

## Open questions

1. Should merge offer a name-rename step (pick survivor *and* rename) in one go,
   or is rename-then-merge via separate actions enough? Assumed: separate.
