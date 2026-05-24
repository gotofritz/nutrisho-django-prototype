# Plan 002: HTMX and Tailwind CSS

## Status: Done

## Goal

Lay the foundation for dynamic inline editing (Plan 004). This plan wires up
HTMX and Tailwind CSS — infrastructure only, no editing UI yet.

## Step 1: HTMX

### 1.1 Dependency and middleware

Add `django-htmx` to `pyproject.toml`. Configure middleware in `settings.py`.
Use the JS bundled with `django-htmx` via `{% django_htmx_script %}` template tag.

Files changed:
- `pyproject.toml`
- `src/nutrisho/settings/base.py` — add `django_htmx` to `INSTALLED_APPS` and middleware
- `src/recipes/templates/recipes/base.html` — add `{% django_htmx_script %}` tag

### 1.2 Partial templates

HTMX swaps HTML fragments. Extract recipe body into a single content partial so
views can return a fragment (no `<html>`/`<body>`) on HTMX requests.

Files changed:
- `src/recipes/templates/recipes/partials/_recipe_content.html` (new)
- `src/recipes/templates/recipes/recipe.html` — delegates to partial via `{% include %}`
- `src/recipes/views/recipe.py` — returns partial template on `request.htmx`

## Step 2: Tailwind CSS

Production-ready build pipeline via pnpm. No CDN.

- Tailwind CSS v4 with `@tailwindcss/cli`
- Input: `src/recipes/static/css/tailwind.css` (CSS-first `@import "tailwindcss"`)
- Output: `src/recipes/static/css/output.css` (gitignored build artifact)
- `package.json` with `css` and `css:watch` scripts

Files changed:
- `package.json` (new)
- `pnpm-lock.yaml` (new)
- `src/recipes/static/css/tailwind.css` (new)
- `Taskfile.yml` — add `css` and `css-watch` tasks delegating to pnpm
- `src/recipes/templates/recipes/base.html` — link `output.css` before `style.css`
- `.gitignore` — add `node_modules/` and `output.css`

## TDD cycles

1. Test: HTMX middleware injects `request.htmx` attribute
2. Test: view returns partial HTML (no `<html>`/`<body>` tags) when request has `HX-Request` header
3. Test: base template renders without error
