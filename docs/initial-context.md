# Initial Context

## Overview

Nutrisho is a Django recipe manager prototype. Stores recipes, ingredients, cuisines, and tags. Supports bulk YAML import and export.

## Tech Stack

- **Runtime**: Python 3.14
- **Framework**: Django 6.0
- **Frontend**: HTMX 2.x (via django-htmx) — inline partial swaps, no full-page reloads
- **DB**: SQLite (dev)
- **Deps**: uv
- **Lint**: ruff
- **Types**: ty
- **Tasks**: Taskfile
- **Tests**: pytest + pytest-django

## Prerequisites

- `uv` — dependency manager and task runner for Python
- `task` — Taskfile runner (`brew install go-task` / `go install github.com/go-task/task/v3/cmd/task@latest`)
- `jq` — required by `.claude/hooks/` for JSON parsing (`brew install jq` / `apt install jq`)

## Project Layout

```
src/
  nutrisho/      # Django project (settings, urls, wsgi)
  recipes/       # Main app: models, views, templates, management commands
    services/      # Pure query/mutation functions, no HTTP (ingredient_admin.py)
    templatetags/  # Custom template filters (recipe_filters.py)
    utils/         # Framework-free helpers (filename.py, sequencing.py, pluralise.py,
                   #   step_title.py)
docs/
  initial-context.md   # this file
  plans/               # active work plans
  archive/             # completed plans
tests/
  conftest.py
  recipes/             # recipe app tests
```

## Architecture

Single Django app (`recipes`) under `src/` layout. No API layer. Frontend is server-rendered Django templates with HTMX inline editing. Debug toolbar enabled in dev.

### Inline Editing Pattern

Each editable entity (field, step, ingredient, group) has three endpoints:
- `GET /<entity>/` — read-only partial (`_*_display.html`)
- `GET /<entity>/edit/` — edit widget partial (`_*_edit.html`)
- `POST /<entity>/save/` — validates and saves; returns display partial on success, edit partial with errors on failure

HTMX swaps partials in place (`hx-swap="outerHTML"`). The `+ Add` buttons (`hx-post`, `hx-swap="beforeend"`) only render a blank edit form — no row is created until its Save posts to the entity's `POST /<entity>/create/` endpoint and validation passes. The draft form submits its DOM `position` (computed at submit via `hx-on::config-request`) and the server inserts at that position (resolved against the ordered sibling list — importer-seeded sequences may be 1-based or gapped), shifting later rows, so saving multiple drafts out of order cannot diverge from the on-screen order; Cancel on an unsaved form just removes it from the DOM, so canceled adds leave no orphan rows. `Delete` buttons use `hx-post` with `hx-swap="outerHTML"`. CSRF token is injected globally via `hx-headers` on `<body>`. HTMX library is served from `django_htmx` static files (`htmx.min.js`).

Ingredient name edit uses an HTML5 `<datalist>` for autosuggest (all existing ingredient names). On save, `ingredient_name` is resolved via get-or-create so renaming creates a new `Ingredient` rather than mutating a shared one.

### Ingredient Clean-up Tool (`recipes/services/`, `recipes/views/ingredient_admin.py`)

A self-contained subsystem under `/recipes/ingredients/manage/`, separate from both
the per-recipe inline editor and Django admin. `Ingredient` rows are shared by every
recipe, so this is where duplicates and spelling variants get edited, deleted or
merged. Login-only, like the rest of the app; the `manage/` URL prefix keeps it clear
of the per-recipe `<recipe_id>/ingredients/...` routes.

The UI is four Miller columns — actions, ingredients, matching recipes, recipe
preview. Clicking an action collapses columns 2-4 into a full-width workspace panel
and turns the clicked button into Cancel. Column 4 is a fresh inert template, not a
trimmed `partials/_recipe_content.html`: that one pulls in the navbars and its field
includes carry `hx-get` edit triggers.

Column 4 follows column 3 rather than holding state of its own: every response
that rebuilds the matches rebuilds the preview with it. Exactly one match previews
itself — there is nothing else to pick — and any other count clears the pane, so a
preview can never outlive the matches it came from.

**Services layer.** `recipes/services/ingredient_admin.py` holds pure query and
mutation functions with no HTTP concerns, so the HTMX views stay thin and the
behaviour is testable without a client. Views own request parsing, guards and
partial selection; services own the ORM.

**Selection lives in the request.** Checkboxes post `ingredient_ids`; every
re-rendered partial echoes them back. There is no client-side store: a change or a
search refreshes its own column and swaps the other affected fragments out of
band, so header counts, the tri-state select-all box and the enabled/disabled
state of Edit/Delete/Merge are all server-rendered. The column-2 header carries
the subsystem's only JavaScript, four lines of it, because `indeterminate` is a
DOM property with no HTML attribute and the dashed state cannot be rendered any
other way. The handler binds to the header wrapper rather than the checkbox:
htmx fires `htmx:load` on the root of swapped content and events bubble up, so a
listener on the nested input never sees it. The workspace carries the selection as
hidden inputs, since it replaces the column holding the checkboxes. `hx-include`
must name the inputs themselves (`.ingredient-pick:checked`, `.workspace-pick`) —
pointing it at a container element sends nothing.

**Repointing rule (important).** `IngredientInRecipe.ingredient` *and* `.substitute`
are both `on_delete=PROTECT`. No ingredient can be deleted while either FK
references it, so `delete_ingredients` and `merge_ingredients` repoint **both** onto
the replacement or survivor inside one transaction before deleting. Repointing an FK
leaves `index_in_sequence` alone, so recipe ordering is unaffected and
`utils/sequencing.py` is not involved. A delete with no usable replacement answers
422 and writes nothing rather than letting PROTECT surface as a 500. A recipe that
already held the survivor and a victim keeps both rows; de-duplicating a group is
out of scope.

**Orphans.** `search_ingredients(query, unused_only=True)` lists ingredients no
`IngredientInRecipe` references as either ingredient or substitute — the rows that
can be deleted outright, since neither FK PROTECTs them. Nothing prunes them
automatically: renames (`get_or_create` keeps the old row), last-use deletions and
imports all leave orphans, and deciding they are junk is the owner's call.

**Saving an edit.** The Edit workspace holds one panel per selected ingredient,
each posting itself. Saving the only panel closes the workspace (via `HX-Retarget`
onto `#columns`, since the form targets itself) — re-rendering a lone panel looks
like nothing happened. Saving one of several marks it and leaves the rest open,
because closing would discard whatever is typed in them; the panels carry the
selection so the view can tell the two cases apart.

**Owner scoping.** Recipes are owner-scoped and column 3 stays that way, but
ingredients are global: the delete confirmation counts affected recipes across all
owners, since a delete reaches recipes the current user cannot see.

**Canonical names.** British spelling wins, enforced by
`UniqueConstraint(Lower("ingredient_name"), name="ingredient_name_ci_unique")`
(migration 0013) and mirrored in `IngredientForm`, which points a clashing rename at
the merge action. Databases predating the constraint are cleaned up with the
`find_ingredient_duplicates` command, which lists case-only clashes; merge them
before migrating.

**Three variant classes.** Case (`Onion`/`onion`) is the constraint above.
**Plural** (`onion`/`onions`) is the third: since the plural is a display form,
an `onions` row is bad data, so `find_plural_duplicates` pairs each row with the
row spelling out its `plural`, `search_ingredients(plurals_only=True)` narrows
column 2 to those pairs (composing with the query and the unused filter), and
`find_ingredient_duplicates` reports both classes. Back-filling is a merge in
the tool, never a data migration: picking which row survives is the owner's
call.

**Merge plural** is the fourth column-1 action and the one that fixes such a
pair. `merge_plural_ingredients` repoints recipes exactly as `merge_ingredients`
does, then writes the deleted row's name **verbatim** onto the survivor's
`plural_name` — the point of the action, since a plain merge drops the spelling
and leaves the rule to guess (`chili`/`chilis` would come back as `chilies`).
Verbatim even when the rule agrees, so the plural column visibly shows where the
merged name went; any prior override is overwritten, the merge being the later
and more deliberate statement. `suggest_singular` preselects whichever half
pluralises into the other, falling back to the first. Capped at **exactly two**
selected: with two plural rows there is no way to tell which spelling wins.
`_SELECTION_BOUNDS` carries each action's `(minimum, maximum)`; every other
action is still minimum-only. **Alias** — variants differing by more than case (`eggplant` →
`aubergine`) — is future work resolving on *input*: an `IngredientAlias` lookup
table applied at write time, so storage and display stay canonical. See
`docs/plans/008-ingredient-aliases.md`.

**Column-2 filters.** The views carry them as one typed mapping (`_Filters`:
`query`, `unused_only`, `plurals_only`), forwarded as `**filters` into the
context helpers, so adding a filter does not widen every call site.

Deleting the last `IngredientInRecipe` in a group, or moving every row out of it
via reassign, deletes the now-empty `IngredientGroup` too (`_prune_empty_group`),
compacting the remaining group indexes. A recipe's **last** group is always kept,
empty or not: the "+ Add ingredient" button is rendered inside a group block, so a
recipe with zero groups could only be refilled by adding a group first. The delete
response carries an `hx-swap-oob="delete"` for the vanished block plus a refreshed
reassign `<select>`, since the row swap alone would leave both stale.

### Step Titles (`Step.step_title`, `recipes/utils/step_title.py`)

Scraped recipes bury the heading of a step in the step itself — `<u>RAGÚ</u>:
Sauté the beef`, or `FOR THE STOCK: soak the kombu`. That heading is structure,
so it lives in its own optional field and the templates render it underlined
with a colon after it — the shape the scraped text wrote by hand — while the
colon itself stays outside `.step-title`, being punctuation rather than heading.
A step without a title renders exactly as it did before. Titles carry **no markup**: the `<u>` was
a wrapper around the heading, never part of it, so `_step_display.html` escapes
the title outright while `step_text` still goes through `safe_step_html`.

`recipes/utils/step_title.py` holds the recognition rule as a pure function,
free of Django imports. It is deliberately narrow — an inline-tag wrapper
(`<u>`, `<b>`, `<i>`, `<s>`) or an entirely upper-case run, closed by a colon,
followed by whitespace and something left over — so `Add salt: to taste` stays
whole. `sentence_case_heading` sits next to it and un-shouts a heading that is entirely
upper case (`FOR THE STOCK` → `For the stock`), leaving anything cased by hand
alone; proper nouns are lost with the shouting, since nothing in the text says
which words they were. Nothing calls either at import time: splitting and
un-shouting are a one-off backfill (`scripts/backfill_step_titles.py`), because
deciding that a colon introduces a heading is a judgement about legacy data, not
an import rule.

In YAML a step is **either** a bare string (untitled — the shape every file used
before) **or** a `{title, text}` mapping. Export emits the mapping only when a
title is set, so untitled recipes round-trip byte-identically; the importer
normalises both shapes in `_normalize_steps` before the write phase, so a
mapping missing `text` fails validation rather than mid-transaction.

### Sequencing (`recipes/utils/sequencing.py`)

All `index_in_sequence` mutations go through shared, transactional helpers:
`insert_at_index` (create at a DOM position), `remove_and_compact`
(delete + close the gap), `move_in_sequence` (swap with a neighbour via a
`-1` sentinel for SQLite's per-statement unique checks). Entity views must
not reimplement index arithmetic.

Empty text fields (`short_description`, `group_name`, `unit`,
`preparation`) are stored as `""`, never `NULL`; YAML export serializes
them as `null` and import coerces `null` back to `""`.

### Template Filters (`recipes/templatetags/recipe_filters.py`)

- `safe_step_html` — sanitizes step text, allowing only `<b>`, `<i>`, `<s>`, `<u>` inline tags; escapes everything else. Applied in `_step_display.html`.
- `format_quantity` — strips trailing decimal zeros from `DecimalField` values (e.g. `2.50 → 2.5`, `4.00 → 4`). Applied in `_ingredient_display.html`.
- `display_ingredient_name` — the ingredient's name, pluralised when the quantity
  calls for it. Takes the whole `IngredientInRecipe`, since the decision needs
  name, quantity and unit together. Applied in `_ingredient_display.html` and
  `ingredient_admin/_recipe_preview.html`. See **Pluralisation** below.

### Pluralisation (`recipes/utils/pluralise.py`, `Ingredient.plural`)

A plural is the display form of **one** ingredient at a quantity other than 1,
never a second row: `1 onion` and `2 onions` are the same `Ingredient`. It is
therefore presentation, computed on render, and nothing persists or exports it —
`export_recipes_to_yaml` always writes the canonical singular.

`recipes/utils/pluralise.py` holds the rule as a pure function with no Django
imports, so it is testable on its own. It inflects the **last word only**
(`spring onion` → `spring onions`) and leaves names already ending in `-s`
alone, since food nouns ending in `-s` are nearly always already plural or mass
(`oats`, `chives`, `asparagus`). `Ingredient.plural` layers the `plural_name`
override on top: blank derives from the rule, a value wins verbatim, and a value
equal to the singular makes the noun invariant (`broccoli`, `fish`). The
override is what covers the irregulars the rule deliberately does not chase, and
it is editable in the clean-up tool's Edit panel.

Two conditions gate the swap, both in `display_ingredient_name`: the quantity is
recorded and is not 1, **and** `unit` is empty. The unit check is what keeps mass
nouns safe — `200 g onion` must never become `200 g onions`. This matters
because `recipe_scale` *persists* scaled quantities, so doubling a recipe writes
`quantity=2` and the page would otherwise read "2 onion".

### Key Models

- `Recipe` — core entity, owns name, description, cuisine, source, owner, servings (author's intended serving count; mandatory, NOT NULL, defaults to 1, constrained to `>= 1`)
- `Ingredient`, `IngredientGroup`, `IngredientInRecipe` — ingredient hierarchy; `IngredientInRecipe.quantity` is stored as-is from source data (not normalized to per-serving). `Ingredient` rows are global (not owner-scoped) and `ingredient_name` is unique case-insensitively; `Ingredient.plural_name` is an optional display-only override for the pluralisation rule (blank derives it); `IngredientInRecipe.ingredient` and `.substitute` are both `PROTECT`
- `Step` — ordered recipe steps; `step_title` is an optional heading, stored as `""` when absent and rendered underlined in front of the step text, followed by a colon
- `Cuisine`, `Source`, `Tag` — lookup/classification models

### Data Flow

YAML files → `batch_load_yaml_recipes` management command → Django ORM → SQLite (always inserts; `id` field in YAML ignored)

Django ORM → `export_recipes_to_yaml` management command → YAML files

`delete_recipe --id <N>` removes recipes by primary key for post-import cleanup


## Constraints

- Prototype quality: no production settings, no secrets management
- SQLite only; no migrations for external DBs
- No REST API yet
- Auth uses Django's built-in User model

## Boundaries

- `src/nutrisho/` — project config only, no business logic
- `src/recipes/` — all domain logic
- `src/recipes/services/` — pure query/mutation functions; no HTTP, no templates
- Management commands in `src/recipes/management/`

## Dev Workflow

```bash
source .venv/bin/activate
task qa          # lint + typecheck + test
```

See AGENTS.md for full TDD workflow.
