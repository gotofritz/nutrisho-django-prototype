# Plan 001: Servings Normalisation, Recipe CRUD, HTMX Inline Editing

## Status: Draft

## Context

The app has ~340 recipes loaded from YAML into the DB. Additionally, some
recipes exist only in the DB (not in the repo as YAML files). The YAML files
all show `serves: 1` — quantities were pre-normalised to a single serving
during an earlier XML-to-YAML conversion — but not all `serves: 1` values are
accurate, and DB-only recipes may have different serving counts. Manual cleanup
of servings data will be required.

The loader (`batch_load_yaml_recipes.py:74`) reads `serves` but discards it.
The template hardcodes "Serves 4". There is no way to create, update, or
delete recipes through the UI — only a partially-built edit form with a
commented-out POST handler. No HTMX integration exists.

There is no CLI command to export recipes back to YAML, which is needed for
the cleanup workflow: export → manually fix servings/quantities → re-import.

## Goals

1. Store per-serving quantities **and** a servings count so the UI can display
   scaled amounts for any number of servings
2. Full CRUD for recipes via the web UI
3. HTMX-powered inline editing — click a field, edit in place, save without
   full page reload

## Development approach: TDD (Red/Green/Refactor)

All implementation follows strict TDD cycles:

1. **Red** — Write a failing test that describes the desired behaviour. Run it,
   confirm it fails for the right reason.
2. **Green** — Write the minimum code to make the test pass. No more.
3. **Refactor** — Clean up duplication, improve naming, extract helpers — tests
   must stay green.

### Practical guidelines

- **Test first, always.** No production code without a failing test driving it.
  This applies to models, views, management commands, template filters, and
  forms alike.
- **Small cycles.** Each red/green/refactor cycle should touch one behaviour.
  E.g. "export command writes correct YAML for a recipe with one ingredient
  group" is one cycle; "...with multiple groups" is the next.
- **Test naming:** `test_<unit>_<scenario>_<expected>` — e.g.
  `test_export_command_single_recipe_writes_yaml_file`.
- **Fixtures in conftest.** Use `conftest.py` with pytest fixtures (faker,
  polyfactory) to build test data. No class-based tests.
- **Django test client for views.** For HTMX endpoints, assert on response
  content (partial HTML), status codes, and headers (`HX-Redirect`, etc.).
- **Don't skip the refactor step.** After green, look for duplication between
  the new code and existing code. Extract shared logic only when the tests
  reveal it — not speculatively.
- **Commit rhythm:** One commit per completed red/green/refactor cycle (or a
  small batch of related cycles). Each commit should have passing tests.

---

## Step -1: Test infrastructure bootstrap

Before the first red test can run, set up the test tooling:

- Add `pytest`, `pytest-django`, `faker`, `polyfactory` to dev dependencies
- Create `pyproject.toml` `[tool.pytest.ini_options]` section with
  `DJANGO_SETTINGS_MODULE = "nutrisho.settings"`
- Create `src/recipes/tests/__init__.py`
- Create `src/recipes/tests/conftest.py` with shared fixtures (recipe factory,
  ingredient factory, user fixture)
- Verify `task test` runs pytest and exits 0 with no tests collected

This is a one-time setup commit — no red/green cycle needed since there's no
behaviour to test yet.

---

## Step 0: YAML export command (for data cleanup)

### 0.1 Management command: `export_recipes_to_yaml`

Add `src/recipes/management/commands/export_recipes_to_yaml.py`. This is the
inverse of `batch_load_yaml_recipes` — reads from DB, writes YAML files.

Usage:
```bash
python manage.py export_recipes_to_yaml recipes_yaml/          # all recipes
python manage.py export_recipes_to_yaml recipes_yaml/ --id 42  # single recipe
python manage.py export_recipes_to_yaml recipes_yaml/ --missing-only  # DB-only recipes not already on disk
```

Output format must match the existing YAML schema exactly so files round-trip
cleanly through the loader. Each file named `{recipe_name}.yml`.

This command is needed **before** the servings work so the cleanup workflow is:
1. Export all recipes (including DB-only ones) to YAML
2. Manually review and fix `serves` values and quantities
3. Re-import with the updated loader

TDD cycles:
1. Test: calling command with empty DB writes no files → implement empty command
2. Test: single recipe with one group/ingredient produces expected YAML
   structure → implement core serialisation
3. Test: `--id` flag exports only that recipe → add filtering
4. Test: `--missing-only` skips recipes that already have a YAML file on disk
5. Test: recipe name with special characters produces safe filename
6. Test: round-trip (export then re-import) produces identical DB state

Files changed:
- `src/recipes/management/commands/export_recipes_to_yaml.py` (new)
- `src/recipes/tests/test_export_recipes.py` (new)
- `src/recipes/tests/conftest.py` (new — shared fixtures)

### 0.2 Taskfile shortcut

Add a `task export` command to `Taskfile.yml` that runs the export with
sensible defaults.

Files changed:
- `Taskfile.yml`

---

## Step 1: Add `servings` to the data model

### 1.1 Migration: add `servings` field to `Recipe`

Add `servings = models.PositiveSmallIntegerField(default=1)` to the `Recipe`
model. Default is 1 as a safe starting point — many existing records have
inaccurate serving data that will need manual cleanup via the export/edit/
re-import workflow (Step 0).

TDD cycles:
1. Test: new Recipe has `servings=1` by default
2. Test: Recipe can be created with explicit servings value

Files changed:
- `src/recipes/models/recipe.py` — add field
- `src/recipes/tests/test_recipe_model.py` (new)
- New migration

### 1.2 Update the YAML loader

In `batch_load_yaml_recipes.py`:
- Stop discarding `serves` (line 74 currently assigns to `_`)
- Switch from `get_or_create` to `update_or_create` for Recipe (and
  IngredientInRecipe, Step, etc.) so that re-importing corrected YAML
  overwrites existing records. This is required for the export → edit →
  re-import cleanup workflow to actually apply fixes.
- Add a `--dry-run` flag that reports what would change without writing to DB,
  so users can preview the effect of a re-import before committing to it.
- Pass `servings=serves` to the Recipe upsert. For existing data this will be
  1, matching the default.

TDD cycles:
1. Test: loading a YAML with `serves: 4` creates Recipe with `servings=4`
2. Test: loading a YAML with `serves: 1` creates Recipe with `servings=1`
3. Test: YAML missing `serves` key defaults to 1
4. Test: re-importing YAML with changed `serves` updates existing Recipe
5. Test: re-importing YAML with changed quantity updates existing ingredient
6. Test: `--dry-run` flag reports changes without modifying DB

Files changed:
- `src/recipes/management/commands/batch_load_yaml_recipes.py`
- `src/recipes/tests/test_batch_load.py` (new)

### 1.3 Clarify the data contract

**Target state** (after manual cleanup):
- `IngredientInRecipe.quantity` stores the amount for **one serving**
- `Recipe.servings` stores the recipe author's intended number of servings
- Display formula: `display_quantity = quantity * recipe.servings`

**Current reality**: quantities in the DB are a mix — most YAML-imported ones
claim to be per-serving (`serves: 1`) but some are inaccurate. DB-only recipes
may have quantities for an unknown number of servings. The export command
(Step 0) and manual review are prerequisites for the data being trustworthy.

Document this contract clearly in model docstrings, including a note that data
accuracy depends on the cleanup having been done.

Files changed:
- `src/recipes/models/recipe.py` — add docstring
- `src/recipes/models/ingredient_in_recipe.py` — add docstring to `quantity`

### 1.4 Template: replace hardcoded "Serves 4"

Replace `<h3 class="serves">Serves 4</h3>` with
`<h3 class="serves">Serves {{ recipe.servings }}</h3>`. This is a read-only
first pass; the HTMX step later makes it interactive.

Files changed:
- `src/recipes/templates/recipes/recipe.html`

### 1.5 Display scaled quantities

Multiply `ingredient.quantity` by `recipe.servings` for display. Options:
- **Template filter** (simplest): `{{ ingredient.quantity|scale:recipe.servings }}`
- **Model property**: `IngredientInRecipe.display_quantity(servings)` — better
  if reused elsewhere

Go with a custom template filter for now. Keep it simple.

TDD cycles:
1. Test: `scale` filter with quantity=2.5 and servings=4 returns 10.0
2. Test: `scale` filter with None quantity returns empty string
3. Test: `scale` filter with servings=1 returns original quantity
4. Test: recipe detail page renders scaled quantities (integration test with
   Django test client)

Files changed:
- `src/recipes/templatetags/recipe_filters.py` (new)
- `src/recipes/tests/test_template_filters.py` (new)
- `src/recipes/templates/recipes/recipe.html`

---

## Step 2: Integrate HTMX

### 2.1 Add HTMX dependency

Add `django-htmx` to `pyproject.toml`. Configure middleware in `settings.py`.
Include the HTMX JS in `base.html` (CDN or vendored — vendored preferred for
offline dev).

Files changed:
- `pyproject.toml`
- `src/nutrisho/settings.py` — add `django_htmx` to INSTALLED_APPS, middleware
- `src/recipes/templates/recipes/base.html` — add `<script>` tag

### 2.2 Partial templates

HTMX swaps HTML fragments. Extract each editable region into its own partial
template so views can return just that fragment:

```
templates/recipes/partials/
  _recipe_name.html        — recipe title (view + edit states)
  _description.html        — short description
  _step.html               — single step row
  _ingredient.html         — single ingredient row
  _ingredient_group.html   — group header + its ingredients
  _servings.html           — servings selector
```

Each partial has two modes controlled by a context flag or separate
`_FOO_edit.html` / `_FOO_display.html` pair. Prefer the pair approach — less
conditional logic in templates.

Files changed:
- New partial templates (listed above)
- `src/recipes/templates/recipes/recipe.html` — refactor to `{% include %}` partials

---

## Step 3: Recipe CRUD

### 3.1 URL scheme

All mutations use POST. Django only populates `request.POST` for POST
requests — using PUT/DELETE would require custom body parsing and extra CSRF
plumbing for no real benefit in a server-rendered HTMX app. Separate URL
paths distinguish create/update/delete intent.

```
/recipes/                                GET    — list (exists)
/recipes/new/                            GET    — render empty recipe form
/recipes/new/                            POST   — create recipe, redirect to detail
/recipes/<id>/                           GET    — detail (exists)
/recipes/<id>/delete/                    POST   — delete recipe

# HTMX endpoints (return partials)
# Fields
/recipes/<id>/field/<field_name>/           GET  — display partial (read-only)
/recipes/<id>/field/<field_name>/edit/      GET  — edit widget for field
/recipes/<id>/field/<field_name>/save/      POST — save field, return display partial
# Steps
/recipes/<id>/steps/<step_id>/              GET  — display partial (read-only)
/recipes/<id>/steps/<step_id>/edit/         GET  — edit widget for step
/recipes/<id>/steps/<step_id>/save/         POST — update step, return display partial
/recipes/<id>/steps/<step_id>/delete/       POST — remove step
/recipes/<id>/steps/add/                    POST — add step
# Ingredients
/recipes/<id>/ingredients/<iir_id>/         GET  — display partial (read-only)
/recipes/<id>/ingredients/<iir_id>/edit/    GET  — edit widget for ingredient
/recipes/<id>/ingredients/<iir_id>/save/    POST — update ingredient, return display partial
/recipes/<id>/ingredients/<iir_id>/delete/  POST — remove ingredient
/recipes/<id>/ingredients/add/              POST — add ingredient
# Groups
/recipes/<id>/groups/<group_id>/            GET  — display partial (read-only)
/recipes/<id>/groups/<group_id>/edit/       GET  — edit widget for group name
/recipes/<id>/groups/<group_id>/save/       POST — update group name, return display partial
/recipes/<id>/groups/<group_id>/delete/     POST — remove group
/recipes/<id>/groups/add/                   POST — add ingredient group
```

Files changed:
- `src/recipes/urls.py`

### 3.2 Views

Replace the monolithic `recipe_edit` view with granular views. Each HTMX
endpoint returns just its partial. Each endpoint gets its own TDD cycles — test
the response status, content, and side effects before writing the view.

**Field-level views** (three views per field):
```python
def recipe_field_display(request, recipe_id, field_name):
    """GET: return read-only display partial."""

def recipe_field_edit(request, recipe_id, field_name):
    """GET: return edit partial with current value in a form."""

def recipe_field_save(request, recipe_id, field_name):
    """POST: validate, save, return display partial."""
```

The display view exists so cancel buttons and successful saves can swap back
to the read-only state without reloading the full page.

**Collection views** for steps, ingredients, groups follow the same three-view
pattern: `/` (GET display), `/edit/` (GET edit widget), `/save/` (POST),
plus `/add/` (POST) and `/delete/` (POST). All mutations are POST so Django's
`request.POST` and CSRF handling work out of the box.

Use `require_GET` for display/edit views, `require_POST` for save/add/delete
views. The create view (`/recipes/new/`) handles both GET and POST, so use
`require_http_methods(["GET", "POST"])` there instead.

For the **Create** flow: GET `/recipes/new/` renders an empty form. POST
`/recipes/new/` validates and creates the Recipe, then redirects to the detail
page where the user continues editing inline. Same view handles both methods.

For **Delete**: POST with confirmation. Return `HX-Redirect` header to send
user back to the list.

TDD cycles (per endpoint family, example for fields):
1. Test: GET display endpoint returns read-only partial (no form elements)
2. Test: GET edit endpoint returns edit partial with current value in input
3. Test: POST save endpoint with valid data saves and returns display partial
4. Test: POST save endpoint with invalid data returns form with errors
5. Test: GET/POST for non-existent recipe returns 404
6. Test: POST save without CSRF token returns 403
7. Test: edit partial's cancel button has `hx-get` pointing to display
   endpoint (not edit) and `hx-swap="outerHTML"` targeting the enclosing
   form — so the swap replaces the whole form with the read-only partial,
   not just the button itself
8. Repeat pattern for steps, ingredients, groups
9. Test: POST to `/recipes/new/` with valid name creates recipe, redirects
10. Test: POST to delete endpoint removes recipe, returns HX-Redirect
11. Test: POST delete step reorders remaining steps' `index_in_sequence`

Files changed:
- `src/recipes/views/recipe.py` — refactor heavily
- `src/recipes/views/recipe_fields.py` (new) — HTMX field endpoints
- `src/recipes/views/recipe_steps.py` (new) — HTMX step endpoints
- `src/recipes/views/recipe_ingredients.py` (new) — HTMX ingredient endpoints
- `src/recipes/tests/test_views_fields.py` (new)
- `src/recipes/tests/test_views_steps.py` (new)
- `src/recipes/tests/test_views_ingredients.py` (new)
- `src/recipes/tests/test_views_crud.py` (new)

### 3.3 Replace the old form

The current `RecipeEditForm` is a monolithic ModelForm that tries to handle
steps and ingredients via dynamic field generation. This doesn't fit the
HTMX inline-edit model. Replace with small, focused forms:

- `RecipeFieldForm` — single-field form for name, description, cuisine, etc.
- `StepForm` — one step
- `IngredientInRecipeForm` — one ingredient row
- `IngredientGroupForm` — group name

TDD cycles:
1. Test: `RecipeFieldForm` validates recipe_name max length
2. Test: `StepForm` rejects empty step_text
3. Test: `IngredientInRecipeForm` accepts valid decimal quantity
4. Test: `IngredientInRecipeForm` rejects negative quantity
5. Test: `IngredientGroupForm` accepts blank group_name (unnamed groups exist)

Files changed:
- `src/recipes/forms/recipe_edit_form.py` — delete or archive
- `src/recipes/forms/field_forms.py` (new)
- `src/recipes/forms/step_form.py` (new)
- `src/recipes/forms/ingredient_forms.py` (new)
- `src/recipes/tests/test_forms.py` (new)

### 3.4 Inline edit UX

Each display element gets HTMX attributes. All mutations use `hx-post` so
Django's standard `request.POST` and `{% csrf_token %}` work without extra
configuration.

```html
<!-- display partial: click to switch to edit mode -->
<span hx-get="/recipes/5/field/recipe_name/edit/" hx-swap="outerHTML"
      class="editable">
  {{ recipe.recipe_name }}
</span>

<!-- edit partial (returned by GET /edit/) -->
<form hx-post="/recipes/5/field/recipe_name/save/" hx-swap="outerHTML">
  {% csrf_token %}
  <input name="recipe_name" value="{{ recipe.recipe_name }}">
  <button type="submit">Save</button>
  <button hx-get="/recipes/5/field/recipe_name/" hx-swap="outerHTML"
          type="button">Cancel</button>
</form>
<!-- Cancel GETs the display partial (not /edit/), restoring read-only view.
     Save POSTs to /save/ which also returns the display partial on success. -->
```

Steps and ingredients follow the same pattern but also support add/remove via
separate `hx-post` endpoints (`/add/`, `/delete/`).

### 3.5 Servings adjuster (HTMX)

The servings display becomes interactive:

```html
<span hx-get="/recipes/5/field/servings/edit/" hx-swap="outerHTML">
  Serves {{ recipe.servings }}
</span>
```

The edit partial shows +/- buttons or a number input. On save, the view
recalculates no stored data (quantities stay per-serving) — it just updates
`recipe.servings` and returns the new display partial. The ingredient list
also refreshes via `hx-trigger="servingsChanged from:body"` or an OOB swap.

---

## Step 4: List page improvements

### 4.1 Create button

Add a "New Recipe" button to the home page linking to `/recipes/new/`.

### 4.2 Delete from list

Each recipe row gets a delete button. Uses `hx-post` to the `/delete/`
endpoint with `hx-confirm` for safety. The form includes `{% csrf_token %}`.
On success, the row is removed from the DOM.

Files changed:
- `src/recipes/templates/recipes/home.html`
- `src/recipes/views/home.py`

---

## Step 5: Clean up and QA

### 5.1 Remove legacy code

- Delete `scripts/sql_to_edit_recipes_hack/`
- Remove the old monolithic edit form if fully replaced
- Remove the `/update` URL route (currently unused)

### 5.2 Test coverage audit

Since TDD is used throughout, tests already exist for all production code by
this point. This step is a **gap analysis** — review coverage and fill any
holes:

- Run `task test -- --cov` and check for uncovered branches
- Add edge-case tests missed during TDD cycles (e.g. empty recipe, recipe with
  no ingredients, concurrent edits, invalid field names in URL)
- Verify HTMX partials return no full-page layout (no `<html>`, `<body>` tags)
- Smoke-test the full export → edit → re-import round-trip

### 5.3 Linting and type checking

Run `task qa` — ruff + ty must pass.

---

## Implementation order

| Order | Step | Depends on | Effort |
|-------|------|-----------|--------|
| 0 | -1 Test infrastructure bootstrap | — | S |
| 1 | 0.1–0.2 YAML export command | 0 | M |
| 2 | 1.1–1.2 Servings field + loader | 0 | S |
| 3 | — **Manual data cleanup** (export, review, re-import) — | 1, 2 | Manual |
| 4 | 1.3–1.5 Docstrings + template + filter | 2 | S |
| 5 | 2.1 HTMX setup | — | S |
| 6 | 2.2 Partial templates | 5 | M |
| 7 | 3.1–3.2 URL scheme + views | 6 | L |
| 8 | 3.3 New forms | 7 | M |
| 9 | 3.4 Inline edit UX | 6, 7, 8 | L |
| 10 | 3.5 Servings adjuster | 4, 9 | M |
| 11 | 4.1–4.2 List page | 7 | S |
| 12 | 5.1–5.3 Cleanup + coverage audit | all | M |

S = small (single commit), M = medium (2–3 commits), L = large (multiple commits)

## Open questions

1. **Authentication**: Should CRUD require login? The `owner` FK exists but
   auth isn't wired up. Suggest deferring auth to a separate plan and keeping
   CRUD open for now (single-user prototype).
2. **Servings UX**: Should changing servings be a **persistent** save (updates
   `recipe.servings` in DB) or **ephemeral** (client-side scaling, DB
   unchanged)? Suggest: persistent for the recipe author's default, ephemeral
   for viewer scaling — but ephemeral needs JS. Start with persistent-only.
3. ~~**Bulk re-import**~~: Resolved — Step 1.2 now switches the loader to
   `update_or_create` so re-imports overwrite existing records.
4. **DB-only recipes**: Some recipes exist in the DB but have no YAML file in
   the repo. The export command (Step 0) must capture these. Decide whether
   exported files should be committed to the repo or kept separate.
5. **Data trust**: Until manual cleanup is done, the servings display will be
   inaccurate for some recipes. Consider showing a visual indicator (e.g.
   "unverified") for recipes where `servings=1` might be a placeholder rather
   than a real value — or skip this and just prioritise the cleanup.
