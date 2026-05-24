# Plan 002: HTMX and Tailwind CSS

## Status: Draft

## Goal

Add dynamic inline editing via HTMX. Add Tailwind CSS for styling. Both are prerequisites for Recipe CRUD (Plan 004).

## Step 1: HTMX

### 1.1 Dependency and middleware

Add `django-htmx` to `pyproject.toml`. Configure middleware in `settings.py`.
Vendor the HTMX JS file (preferred over CDN for offline dev).

Files changed:
- `pyproject.toml`
- `src/nutrisho/settings.py` — add `django_htmx` to `INSTALLED_APPS` and middleware
- `src/recipes/templates/recipes/base.html` — add `<script>` tag for HTMX

### 1.2 Partial templates

HTMX swaps HTML fragments. Extract each editable region into its own partial:

```
templates/recipes/partials/
  _recipe_name.html
  _description.html
  _step.html
  _ingredient.html
  _ingredient_group.html
  _servings.html
```

Each partial has display and edit variants (`_FOO_display.html` / `_FOO_edit.html`).
Prefer the pair approach — less conditional logic in templates.

Files changed:
- New partial templates (listed above)
- `src/recipes/templates/recipes/recipe.html` — refactor to use `{% include %}` partials

## Step 2: Tailwind CSS

- Add `tailwindcss` CLI to project (or use CDN play build for prototype)
- Create `tailwind.config.js` pointing at template files
- Add `task css` to Taskfile for watching/compiling
- Replace inline styles and legacy CSS with Tailwind utility classes

Files changed:
- `tailwind.config.js` (new)
- `Taskfile.yml` — add `css` and `css-watch` tasks
- `src/recipes/templates/recipes/base.html` — link compiled CSS

## TDD cycles

1. Test: HTMX middleware injects `request.htmx` attribute
2. Test: view returns partial HTML (no `<html>`/`<body>` tags) when request has `HX-Request` header
3. Test: base template renders without error
