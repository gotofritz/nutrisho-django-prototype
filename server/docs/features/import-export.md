# Import, export and the clipper endpoint (#78)

Three ways in or out, one importer behind them:

- **Export** (`/recipes/export/`, linked from the Import & export page) downloads
  all of the signed-in user's recipes as one Nutrisho document.
- **Import** (`/recipes/import/`, "Import & export" on the Config page) uploads a
  Nutrisho document or a page's schema.org JSON-LD and lists what came in.
- **`POST /recipes/api/recipes/`** takes the same two formats as a JSON body,
  signed in with an API token. It is what the recipe clipper (`extension/`)
  will call.

`services/recipe_document.py` reads either format into drafts and
`services/recipe_import.py` writes them; `services/recipe_export.py` writes a
document. Nothing else creates recipes in bulk.

## The Nutrisho document

Versioned JSON, `{"format": "nutrisho", "version": 1, ...}`; the shape is in
the `recipe_document.py` docstring. Keys are the models' column names. It holds
every column of every recipe the user owns, trashed ones included
(`deleted_at`), with `created_date`. Text is as typed, inline markup included,
and quantities are decimal strings, so nothing is rounded. Ingredients, units,
tags and the cuisine travel by name (the cuisine as its dotted path), never by
id, so a file moves between servers. The `ingredients` list carries the display
data of every ingredient the recipes use (`plural_name`, `family`,
`dietary_constraint`).

A round trip loses nothing: an export imported by another user, or by the same
user after deleting everything, exports the same document again
(`tests/recipes/test_recipe_import.py`). `tests/recipes/test_recipe_export.py`
fails when a model gains a column the export does not write, until it does or
the test's `NOT_EXPORTED` says why it need not. The importer reads what the
exporter writes, so add the column to both.

Text longer than its column is refused with the path of the field, as in
`document.recipes[0].steps[2].step_title must be at most 128 characters.`, and
long prose (description, step text) longer than the editor's
`PROSE_MAX_LENGTH`. SQLite does not enforce `max_length`, so without the check
a client could store text no form would let anyone save, and the database
could not move to Postgres. The limits are read from the models.

A document from a newer version is refused, not half-read. Bump `VERSION` when
a change would make an older server misread a file; adding an optional key does
not need it, since readers ignore keys they do not know.

## How an import writes

- Every draft becomes a new recipe of the importing user; existing recipes are
  never changed. A name the user already has on a live recipe gets " Imported"
  (" Imported 2", …), as a restored recipe gets " Restored"; the result says
  which were renamed. A recipe imported into the trash keeps its name.
- Ingredient, tag and unit names go through `name_resolution` like typed ones
  (aliases and plurals included). One the user cannot see becomes private to
  them; a new ingredient takes its display data from the document's
  `ingredients` list, while one that is found keeps its own.
- Cuisines are never created, since staff curate them; an unknown cuisine is
  left blank. A size word or an amount phrase in a row's `unit` (`small`, `to
  taste`) never becomes a unit: it is kept as written in `legacy_unit`, where
  `normalise_units` can move it. Both come back as warnings, shown on the page
  and in the endpoint's response.
- Steps, groups and rows take their list order (`sequencing.number_in_order`)
  and are written with `bulk_create`, so `Recipe.save()` still runs for the
  recipe itself and keeps `plain_name` current.
- Each recipe is its own transaction: the whole document is read and checked
  first, so a bad file writes nothing, and a large one does not hold the SQLite
  write lock throughout.

## schema.org JSON-LD

Recipe pages embed a `Recipe` node; `utils/json_ld.py` finds it wherever the
page put it (alone, in a list, in an `@graph`, under `mainEntity`) and reads its
loose shapes. What maps where:

| JSON-LD | Recipe |
| --- | --- |
| `name` | `recipe_name` ("Untitled recipe" when absent) |
| `description` | `short_description` |
| `recipeYield` | `servings`: its first whole number, else 1 |
| `url`, else `mainEntityOfPage` | `source_instance`, dropped if over 200 characters rather than cut into a broken link |
| `recipeCuisine` | `cuisine`, if a node matches it |
| `recipeIngredient` | one unnamed group, a row per line |
| `recipeInstructions` | steps: a `HowToStep`'s `name` is its title when it adds to the text, a `HowToSection`'s name titles its first step, and a block of text is a step per paragraph |

Markup is stripped and entities decoded, and text is cut to fit its column
rather than refused, since a page's length is no fault of the user's. `keywords` and `recipeCategory` are
not made into tags: sites fill them for search engines, and each would become a
private tag. Ingredient lines are split by `utils/ingredient_line.py`: a
quantity (whole, decimal with point or comma, fraction, mixed, `½`, the low end
of a range, noted as written), then a unit from the global vocabulary (parsing
knows no owner, so a user's own unit stays part of the name; only after a
quantity, two words before one, an `of` after it dropped), then the name;
after the first comma comes the preparation, brackets are a note, and a size
or an amount phrase moves as the editor would ask (`unit_words.py`).

## The endpoint and API tokens

`views/api.py` is the app's one JSON endpoint and its one view outside the
session login. A browser extension's requests do not come from a page of this
site, so a session cookie plus CSRF token does not fit them; instead the client
sends `Authorization: Bearer <key>`:

- The view is `@login_not_required` (it is in `PUBLIC_ROUTES`) and
  `@csrf_exempt`. It never looks at the session: a forged cross-site post
  carries the victim's cookie but not their key, so skipping CSRF is safe only
  because of that.
- 201 answers `{"recipes": [{"id", "name", "url", "renamed", "in_trash"}],
  "warnings": [...]}`, each `id` the recipe's UUID as text (#156); 400, 401 (with `WWW-Authenticate: Bearer`), 405 and 413
  answer `{"error": "..."}`. The body limit is Django's
  `DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB).
- `ApiToken` (`models/api_token.py`) stores only the SHA-256 digest of a key;
  the key is `nsh_` plus 43 random characters, shown once. A user may hold
  several; an inactive user's keys stop working, and `last_used_at` is noted on
  each use.
- `make manage ARGS="create_api_token <username> --name clipper"` makes one and
  prints the key. Django admin lists tokens and deletes them to revoke; it
  cannot add one, since it could not show the key. A settings page where users
  make their own is for when the clipper exists.

For the extension: post from the background service worker, which with a host
permission for the server is not subject to CORS, so the server sends no CORS
headers. A content script would be.
