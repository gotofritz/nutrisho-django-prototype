# Plan 004: Recipe CRUD and Inline Editing

## Status: Draft

## Depends on

- Plan 002 (HTMX + Tailwind) — partials and HTMX middleware must exist

## Goal

Full create/read/update/delete for recipes via HTMX-powered inline editing. Replace raw SQL editing. Replace monolithic edit form with granular field-level views.

---

## Step 1: URL scheme

All mutations use POST. Separate URL paths distinguish intent.

```
/recipes/                                GET    — list (exists)
/recipes/new/                            GET    — render empty recipe form
/recipes/new/                            POST   — create recipe, redirect to detail
/recipes/<id>/                           GET    — detail (exists)
/recipes/<id>/delete/                    POST   — delete recipe

# HTMX endpoints (return partials)
# Fields
/recipes/<id>/field/<field_name>/           GET  — display partial
/recipes/<id>/field/<field_name>/edit/      GET  — edit widget
/recipes/<id>/field/<field_name>/save/      POST — save field, return display partial
# Steps
/recipes/<id>/steps/<step_id>/              GET  — display partial
/recipes/<id>/steps/<step_id>/edit/         GET  — edit widget
/recipes/<id>/steps/<step_id>/save/         POST — update step
/recipes/<id>/steps/<step_id>/delete/       POST — remove step
/recipes/<id>/steps/add/                    POST — add step
# Ingredients
/recipes/<id>/ingredients/<iir_id>/         GET  — display partial
/recipes/<id>/ingredients/<iir_id>/edit/    GET  — edit widget
/recipes/<id>/ingredients/<iir_id>/save/    POST — update ingredient
/recipes/<id>/ingredients/<iir_id>/delete/  POST — remove ingredient
/recipes/<id>/ingredients/add/              POST — add ingredient
# Groups
/recipes/<id>/groups/<group_id>/            GET  — display partial
/recipes/<id>/groups/<group_id>/edit/       GET  — edit widget
/recipes/<id>/groups/<group_id>/save/       POST — update group name
/recipes/<id>/groups/<group_id>/delete/     POST — remove group
/recipes/<id>/groups/add/                   POST — add ingredient group
```

Files changed:
- `src/recipes/urls.py`

---

## Step 2: Views

Use `require_GET` for display/edit views, `require_POST` for save/add/delete.
Create view handles both methods via `require_http_methods(["GET", "POST"])`.

**Field-level views:**
```python
def recipe_field_display(request, recipe_id, field_name): ...  # GET — read-only partial
def recipe_field_edit(request, recipe_id, field_name): ...     # GET — edit widget
def recipe_field_save(request, recipe_id, field_name): ...     # POST — save, return display partial
```

Same three-view pattern for steps, ingredients, groups. Mutations also get `/add/` and `/delete/`.

Create flow: GET `/recipes/new/` → empty form. POST → create Recipe, redirect to detail.
Delete flow: POST → remove from DB, return `HX-Redirect` header to list.

TDD cycles (per endpoint family):
1. Test: GET display returns read-only partial (no form elements)
2. Test: GET edit returns edit partial with current value in input
3. Test: POST save with valid data saves and returns display partial
4. Test: POST save with invalid data returns form with errors
5. Test: GET/POST for non-existent recipe returns 404
6. Test: POST save without CSRF token returns 403
7. Test: edit partial cancel button has `hx-get` pointing to display endpoint (not edit)
8. Repeat pattern for steps, ingredients, groups
9. Test: POST to `/recipes/new/` with valid name creates recipe, redirects
10. Test: POST delete removes recipe, returns `HX-Redirect`
11. Test: POST delete step reorders remaining steps' `index_in_sequence`

Files changed:
- `src/recipes/views/recipe.py` — refactor
- `src/recipes/views/recipe_fields.py` (new)
- `src/recipes/views/recipe_steps.py` (new)
- `src/recipes/views/recipe_ingredients.py` (new)
- `tests/recipes/test_views_fields.py` (new)
- `tests/recipes/test_views_steps.py` (new)
- `tests/recipes/test_views_ingredients.py` (new)
- `tests/recipes/test_views_crud.py` (new)

---

## Step 3: New forms

Replace monolithic `RecipeEditForm` with small focused forms:

- `RecipeFieldForm` — single field (name, description, cuisine, etc.)
- `StepForm` — one step
- `IngredientInRecipeForm` — one ingredient row
- `IngredientGroupForm` — group name

TDD cycles:
1. Test: `RecipeFieldForm` validates `recipe_name` max length
2. Test: `StepForm` rejects empty `step_text`
3. Test: `IngredientInRecipeForm` accepts valid decimal quantity
4. Test: `IngredientInRecipeForm` rejects negative quantity
5. Test: `IngredientGroupForm` accepts blank `group_name` (unnamed groups exist)

Files changed:
- `src/recipes/forms/recipe_edit_form.py` — delete or archive
- `src/recipes/forms/field_forms.py` (new)
- `src/recipes/forms/step_form.py` (new)
- `src/recipes/forms/ingredient_forms.py` (new)
- `tests/recipes/test_forms.py` (new)

---

## Step 4: Inline edit UX

```html
<!-- display partial -->
<span hx-get="/recipes/5/field/recipe_name/edit/" hx-swap="outerHTML" class="editable">
  {{ recipe.recipe_name }}
</span>

<!-- edit partial (returned by GET /edit/) -->
<form hx-post="/recipes/5/field/recipe_name/save/" hx-swap="outerHTML">
  {% csrf_token %}
  <input name="recipe_name" value="{{ recipe.recipe_name }}">
  <button type="submit">Save</button>
  <button hx-get="/recipes/5/field/recipe_name/" hx-target="closest form"
          hx-swap="outerHTML" type="button">Cancel</button>
</form>
```

Cancel GETs display partial (not `/edit/`). Save POSTs to `/save/` which returns display partial on success.

### Servings adjuster

```html
<span hx-get="/recipes/5/field/servings/edit/" hx-swap="outerHTML">
  Serves {{ recipe.servings }}
</span>
```

Edit partial shows +/- buttons or number input. Save updates `recipe.servings`; quantities stay per-serving. Ingredient list refreshes via OOB swap or `hx-trigger="servingsChanged from:body"`.

---

## Step 5: List page

- Add "New Recipe" button linking to `/recipes/new/`
- Each recipe row gets delete button: `hx-post` to `/delete/` with `hx-confirm`
- On delete success, row removed from DOM

Files changed:
- `src/recipes/templates/recipes/home.html`
- `src/recipes/views/home.py`

---

## Step 6: Cleanup and QA

- Delete `scripts/sql_to_edit_recipes_hack/`
- Remove old monolithic edit form if fully replaced
- Remove unused `/update` URL route
- Run coverage audit: check for uncovered branches, add edge-case tests
- Verify HTMX partials return no full-page layout (no `<html>`, `<body>` tags)
- Smoke-test full export → edit → re-import round-trip
- Run `task qa` — ruff + ty must pass

---

## Open questions

1. **Auth**: Should CRUD require login? `owner` FK exists but auth not wired up. Suggest defer auth to separate plan; keep CRUD open for now (single-user prototype).
2. **Servings UX**: Persistent save (updates `recipe.servings` in DB) vs ephemeral (client-side scaling)? Start with persistent-only.
