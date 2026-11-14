# Inline editing

## Read mode and edit mode (#58)

A recipe page opens to be read: `recipe` passes `reading=True`, and every
display partial then leaves out its editor trigger, tick box and move buttons,
and the sheet its `+ Add` buttons and selection panels. A tap while scrolling on
a kitchen tablet opens nothing. `?edit=1` is edit mode; Edit recipe and Done
editing, first in the margin, switch between the two, keeping the search in the
query string so previous and next still walk the same list. Edit details shows
in edit mode only. A recipe just created, duplicated, saved from Edit details or
copied at other servings opens in edit mode (`_redirect_to`).

The partial endpoints never set `reading`, so what they return is always
editable: they are only reached from edit mode. A new display partial follows
the same rule (`{% if reading %}…{% else %}…{% endif %}`).

In edit mode each line's trigger is a `<button type="button" class="editable">`
(#60), styled to look like the line, so Tab reaches it and Enter or Space opens
its editor. Escape in an open editor presses its Cancel (`data-escape`), which
puts the line back with focus on it, or drops an unsaved draft. Resting on any
control shows which keys work it ([key hints](browser-code-and-csp.md#key-hints-60)).

`tests/recipes/test_keyboard_access.py` walks the URLconf and parses every page
and partial a staff owner can GET (plus the blank drafts) for what #60 forbids:
an element other than a link, button or form field that starts a request on a
click, a link without `href`, a link or button with no name, and a field with
only a placeholder for a label. A new template is checked as soon as a route
renders it.

## Inline Editing Pattern

Each editable entity (field, step, ingredient, group) has three endpoints:
- `GET /<entity>/` — read-only partial (`_*_display.html`)
- `GET /<entity>/edit/` — edit widget partial (`_*_edit.html`)
- `POST /<entity>/save/` — validates and saves; returns display partial on success, edit partial with errors on failure

The view validates the form, then hands the instance its fields set to a service that writes it under a lock: `save_field` (`services/recipe_metadata.py`, which also holds `create_recipe` and `save_metadata` for the full metadata form), `save_step`/`create_step` (`services/step_editing.py`), and `save_row`/`create_row` and `rename_group`/`create_group` (`services/ingredient_groups.py`). A service raises `ObjectDoesNotExist` when the row has gone (the view answers 404) and a named error the view shows on the form, such as `DuplicateRecipeNameError` for a name the owner already uses.

HTMX swaps partials in place (`hx-swap="outerHTML"`). The `+ Add` buttons (`hx-post`, `hx-swap="beforeend"`) only render a blank edit form — no row is created until its Save posts to the entity's `POST /<entity>/create/` endpoint and validation passes. The draft form submits its DOM `position` (computed at submit by `app.js` from the form's `data-position-*` attributes) and the server inserts at that position (resolved against the ordered sibling list — legacy imported sequences may be 1-based or gapped), shifting later rows, so saving multiple drafts out of order cannot diverge from the on-screen order; Cancel on an unsaved form just removes it from the DOM, so canceled adds leave no orphan rows. `Delete` buttons use `hx-post` with `hx-swap="outerHTML"`. CSRF token is injected globally via `hx-headers` on `<body>`. HTMX library is served from `django_htmx` static files (`htmx.min.js`).

Failed requests are not swapped: the `htmx-config` meta in `base.html` swaps 2xx/3xx and 422 (validation errors re-render the edit form) and marks everything else as an error with `swap: false`, so an open edit form keeps the typed text. One global listener in `app.js` catches `htmx:responseError`, `htmx:sendError` and `htmx:timeout` and shows the fixed `#save-error` banner ("Your change was not saved." for writes, "That did not load." for GETs), with a reload hint on 403/404 (stale CSRF token, row deleted in another tab) and a connection hint on network errors. It is dismissible and hides itself when a later write succeeds. With `DEBUG=True`, django-htmx's debug script replaces the page with Django's error page on a 4xx/5xx before the banner can show, so check the banner with `DEBUG=False`.

Focus and announcements after swaps (#61) also live in `app.js`. htmx itself refocuses an element whose id survives a swap, which is why the ↑/↓ buttons carry stable ids (`step-<id>-up`, `iir-<id>-down`, …) and the cuisine tool's checkboxes `cuisine-pick-<id>`, and it focuses `[autofocus]` in new content: the first field of every inline form gets `autofocus` from its form class (the Cancel button, in the delete panel). Anything else that removes the focused element (Save, Cancel, Delete) would drop focus to `<body>`, so a `htmx:beforeSwap` listener remembers the spot and `htmx:afterRequest` focuses what replaced it (its `.editable` button) or the nearest surviving neighbour; unsaved drafts (`data-cancel-draft`) and panels (`data-close-panel`, back to the toggle named by `aria-controls`) do the same without a request. A form re-rendered with errors focuses its first `aria-invalid` field; the hand-rendered `ingredient_name` and `cuisine_name` inputs set `aria-invalid`/`aria-describedby` themselves, matching Django's own widgets. A boosted page swap focuses the page's `<h1 tabindex="-1">`, or announces the page title when there is none or an `[autofocus]` field took focus.

Announcements go through one polite live region, `#a11y-status`, that is always in the page, since a region swapped in with its text already set is often not read out. It and the `#save-error` banner live in `partials/_page_regions.html`, which `_recipe_content.html` renders again for a boosted visit because that partial replaces the whole `<body>`. The text of any `[data-announce]` element in swapped content (the clean-up tools' counts, "Saved") is read out after settle; views announce what a swap cannot show, such as a deletion, with `announce()` (`recipes/views/_announce.py`), which sets an `announce` event in `HX-Trigger`. Every `.form-error` is `role="alert"`.

Page structure (#74): `base.html` sets `<html lang="en">` and wraps `{% block content %}` in the page's one `<main>`. The recipe page overrides the outer `{% block main %}` instead, because `_recipe_content.html` is also the whole `<body>` of a boosted visit, so it brings its own site header, `<main class="recipe-contents">` (the sheet), the `<aside aria-label="Recipe tools">` margin beside it (Edit details, Scale, Duplicate, Delete and their panels) and the `<nav class="page-turn" aria-label="Recipes">` with previous and next after it. Its outline is the title as `<h1>`, visually hidden `<h2>`s for Method and Ingredients, and each ingredient group as `<h3>`; the staff tools open with a visually hidden `<h1>`. `/` has no page of its own and redirects to `recipes:home`. Form-field edges use `--color-field-border` (`#7a7062`, 4.6:1 on the paper colour, 4.9:1 on white). Each recipe-list row puts the recipe's name first and gives every action a visually hidden copy of it, so the actions are told apart out of context. On the sheet, each row's checkbox and ↑/↓ buttons are named after their row ("Select leek", "Move step Leeks up"; a step is named by its title, or its first words), and the ↑/↓ targets are 24×24px (WCAG 2.5.8). The margin toggles carry `aria-expanded`, which `app.js` keeps in step with whether their panel has content (#60).

Ingredient name edit suggests names through an HTML5 `<datalist>` that starts empty (#80): shipping every name with each edit form cost 114 KB a click at 2,000 ingredients. As the user types, the input asks `recipes:ingredient_suggest` (`hx-trigger="input changed delay:200ms"`, `hx-sync="this:replace"` so a slow answer never lands over a newer one) and swaps the returned `<option>`s into the datalist. `suggest_ingredient_names` (`services/name_resolution.py`) gives the top 20 names the signed-in user sees, those starting with the text before those merely containing it. The `hx-*` attributes live on the form's widgets (`_SUGGESTED_NAME_ATTRS`), and the endpoint reads whichever of `ingredient_name` or `substitute_name` the input sent. On save, `ingredient_name` is resolved via get-or-create so renaming creates a new `Ingredient` rather than mutating a shared one.

The row's optional substitute is typed in `substitute_name` (labelled "Or", sharing the same datalist and autocomplete) and shown as `or X` after the name, pluralised at the same quantity (`2 onions or shallots`). Both names resolve through `resolve_row_names` (`services/ingredient_groups.py`), which `create_row` and `save_row` call inside their transaction: `resolve_ingredient` for each, so aliases, plurals and private rows work alike, and a blank substitute clears it. A substitute that resolves to the ingredient itself (`aubergine or eggplant`) is a form error.

## Ingredient groups

Deleting the last `IngredientInRecipe` in a group, or moving every row out of it
via reassign, deletes the now-empty `IngredientGroup` too (`prune_empty_group` in
`services/ingredient_groups.py`, beside `delete_row`, `delete_group`, `move_row`
and `reassign_rows`),
compacting the remaining group indexes. A recipe's **last** group is always kept,
empty or not: the "+ Add ingredient" button is rendered inside a group block, so a
recipe with zero groups could only be refilled by adding a group first. The delete
response carries an `hx-swap-oob="delete"` for the vanished block plus a refreshed
reassign `<select>`, since the row swap alone would leave both stale.

A recipe's one group may be unnamed; once it has two, each needs a name.
`create_group` and `rename_group` check that with the recipe row locked, so two
tabs cannot both add a blank group, and raise `GroupNameError`, which the view
shows on the form. `IngredientGroupForm` only trims the name.

Deleting a group by hand (`recipe_group_delete`) cascades to its rows, so the
form's Delete button asks first, naming how many ingredients go and pointing to
"Move to"; an empty group is deleted without asking. The same last-group rule
holds: the form hides Delete for a recipe's only group, and the view, under a
lock on the recipe row, swaps the block back in rather than delete it.

Every response that re-renders groups or rows (`_groups_list.html`,
`_iir_list.html`, `_group_block.html`, the clean-up tool's preview) passes the
recipe through `with_ingredients` or the group through `with_rows`
(`services/recipe_contents.py`), after its writes, so it costs the same queries
at any recipe size; `tests/recipes/test_query_counts.py` checks each one on a
small and a large recipe (#64).

## Template Filters (`recipes/templatetags/recipe_filters.py`)

- `safe_step_html` — sanitizes step text, allowing only `<b>`, `<i>`, `<s>`, `<u>` inline tags; escapes everything else. Applied in `_step_display.html`.
- `safe_title_html` — the same for `Recipe.recipe_name`, allowing only `<s>` and `<u>`. Applied wherever the title is rendered as markup (`_field_display.html`, the recipe list, the delete panel, the metadata page, the clean-up tool's columns 3 and 4). Plain-text contexts — the `<title>` element and the `hx-confirm` prompt — use Django's `striptags` instead.
- `safe_blurb_html` — the same for `Recipe.short_description`, allowing `<b>`, `<i>`, `<s>`, `<u>` and turning new lines (and `<br>`) into `<br>`. Applied in `_field_display.html`.

  All three share `_InlineHtmlSanitizer`: tags lose their attributes and come out **balanced** — an unclosed tag is closed at the end and a stray closing tag is dropped — since the fragment lands inside a larger page and an unclosed `<u>` would underline everything after it. The markup is stored as typed; sanitizing happens on render only.
- `format_quantity` — strips trailing decimal zeros from `DecimalField` values (e.g. `2.50 → 2.5`, `4.00 → 4`), always in fixed-point notation. Applied in `_ingredient_display.html` and `_scaled_ingredients.html`.
- `display_ingredient_name` — the ingredient's name, pluralised when the quantity
  calls for it. Takes the whole `IngredientInRecipe`, since the decision needs
  name, quantity and unit together. Applied in `_ingredient_display.html` and
  `ingredient_admin/_recipe_preview.html`. See [pluralisation](pluralisation.md).
- `display_substitute_name` / `substitute_name_at` — the same for the row's
  substitute, at the same quantity.
- `web_url` — a recipe's free-text source when it is a whole http(s) URL, else
  `""`; `_recipe_content.html` links only then, so no other scheme reaches an
  `href`.
- `scaled_quantity` / `ingredient_name_at` — the display-time scaling pair used by
  `_scaled_ingredients.html`: the quantity scaled by the page's `Fraction` and
  rounded for display, and the name pluralised for that displayed quantity. See
  [scaling](scaling.md).
