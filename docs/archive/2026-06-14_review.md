# 001 — Architecture Review

Architectural analysis of the codebase as of branch `fix/list-delete-htmx`
(PR #13). Findings are ordered by priority; each numbered item is a
candidate work package.

## Patterns observed (working well)

- **Layout**: `src/` layout, single Django app (`recipes`), config-only
  `nutrisho/` project. Settings split `base/dev/test/prod` via
  `django-environ`. Tests live outside `src/` in `tests/recipes/`
  (17 files, ~4300 lines, 361 tests).
- **Inline-edit triad**: each editable entity (field, step, ingredient,
  group) exposes `display` / `edit` / `save` endpoints returning partials;
  HTMX swaps `outerHTML`. Consistent across `recipe_fields.py`,
  `recipe_steps.py`, `recipe_ingredients.py`. Template naming consistent
  (`_*_display.html` / `_*_edit.html`).
- **Ordering**: `index_in_sequence` + `UniqueConstraint`, swaps via
  sentinel `-1` inside `transaction.atomic` — correct for SQLite's
  immediate constraint checks.

## Findings

### ✅ 1. Dead legacy code (highest priority, pure deletion)

The pre-plan-004 whole-page edit flow is dead but still shipped:

- `src/recipes/forms/recipe_edit_form.py` (156 lines): legacy
  `RecipeEditForm`. Its `clean()` references `interest_%s` fields that
  exist nowhere — tutorial copy-paste leftover. Contains commented-out
  blocks.
- `src/recipes/views/recipe.py` `recipe_edit`: commented-out save logic;
  builds `RecipeEditForm` that nothing submits anymore (inline editing
  replaced it).
- `src/recipes/urls.py`: `path("<int:recipe_id>/update", recipe, ...)` —
  an "update" route mapped to the read view; `/edit` route serves the dead
  form.
- `src/recipes/templates/recipes/partials/_recipe_content.html`: every
  `{% if form %}` branch is the dead edit mode.
- `src/recipes/templates/recipes/nav_recipe_edit.html`: only included from
  the dead branch.
- `src/recipes/tests.py`: empty placeholder; tests live in `tests/`.
- Tests covering only the dead code: `tests/recipes/test_forms.py`,
  plus `recipe_edit` cases in `test_htmx.py` and `test_views.py`.

### ✅ 2. Triple duplication in entity views

`recipe_steps.py` and `recipe_ingredients.py` (steps / ingredients /
groups) each reimplement: add-with-`Max(index)+1`, delete-then-compact
loop, `move_up`/`move_down`, and `_swap_*_indices`. Roughly 300
near-identical lines. Opportunity: a shared sequencing helper module
parameterized by model + filter kwargs.

### ✅ 3. Missing transactions on multi-row mutations

- `recipe_step_delete` / `recipe_ingredient_delete` /
  `recipe_group_delete`: delete + compact loop without
  `transaction.atomic`. Interruption mid-loop produces index gaps — the
  same corruption class the `fix_duplicate_sequences` command repairs.
- `recipe_ingredient_reassign`: magic temp index `10000 + i`, many
  per-row saves, no transaction — partial failure strands rows.
- `recipe_duplicate`: multi-table copy without a transaction.

### ✅ 4. Exception handling smell

`recipe_crud.py` `recipe_scale`: `except (ValueError, TypeError,
Exception)` — `Exception` swallows everything and makes the tuple
redundant. Should be `(InvalidOperation, ValueError, TypeError)`.

### ✅ 5. Mixed HTMX detection

Most views use `request.htmx` (django-htmx middleware); `recipe_delete`
uses raw `request.headers.get("HX-Request")`. Standardize on
`request.htmx`.

### ✅ 6. No auth/authorization

No `login_required` anywhere; any visitor can edit/delete all recipes.
Owner assigned via hardcoded `User.objects.filter(pk=2)` and model
`default=2`. Acceptable under prototype constraints — must be addressed
before any deployment.

### ✅ 7. Model hygiene (one migration batch when addressed)

- `null=True` on CharFields (`group_name`, `short_description`, `unit`,
  `preparation`) — two empty states; convention is `blank=True` only.
- `IngredientInRecipe.ingredient` uses `on_delete=DO_NOTHING` — dangling
  FK risk; `PROTECT` is safer.
- `Ingredient.family` verbose name is a copy-paste of `Source.source`'s.
- Singular `related_name`s for to-many relations (`recipe.step`,
  `group.ingredient`, `recipe.tag`) read wrong.
- `IngredientInRecipe.natural_key` returns a model instance inside the
  tuple — not serializable.
- Explicit `id = AutoField` on every model overrides
  `DEFAULT_AUTO_FIELD = BigAutoField`.

### ✅ 8. Query efficiency

- Recipe detail iterates groups → ingredients → `ingredient` FK in
  templates without `prefetch_related` — N+1 per render.
- `home` lists all recipes without pagination (fine for prototype).
- `_next_recipe_url` (`recipe_crud.py`) and `_get_recipe_nav`
  (`recipe.py`) duplicate neighbor-recipe logic.

### 9. Minor

- `views/recipe.py` and `views/home.py` lack type hints (violates
  AGENTS.md rule; newer view modules comply).
- `urls.py`: `/edit` and `/update` miss the trailing slash all other
  routes have.
- Test suite takes ~200s for 361 tests; check the test settings use a
  fast password hasher and consider `pytest-xdist`.

## Prioritized work packages

1. ✅ [x] Delete the legacy edit path (finding 1).
2. ✅ [x] Extract shared ordering/sequencing helpers (finding 2).
3. ✅ [x] Wrap multi-row mutations in `transaction.atomic` (finding 3).
4. ✅ [x] Fix `except Exception` in `recipe_scale`; unify HTMX detection
   (findings 4, 5).
5. ✅ [x] Add `prefetch_related` to the recipe detail view (finding 8).
6. ✅ [x] Model cleanups in one migration batch (finding 7).
7. ✅ [x] Authentication/authorization before the prototype graduates
   (finding 6).

## Status notes

- All packages done on `fix/list-delete-htmx`.
- Finding 7 items deferred as out of scope for the prototype:
  singular `related_name` renames (wide template/export churn) and
  removing explicit `id = AutoField` (would rewrite every PK to
  BigAutoField).
