# Import, export and the clipper endpoint (#78)

Three ways in or out, one importer behind them:

- **Export** (`/recipes/export/`, linked from the Import & export page) downloads
  all of the signed-in user's recipes as one Nutrisho document.
- **Import** (`/recipes/import/`, "Import & export" on the Config page) uploads a
  Nutrisho document or a page's schema.org JSON-LD and lists what came in.
- **`POST /recipes/api/recipes/`** takes the same two formats as a JSON body,
  signed in with an API token. It is what the recipe clipper (`extension/`)
  calls.

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
- A cuisine the owner cannot see becomes their own, as in the editor (#171);
  one that cannot be placed (a bare name more than one node has, a fourth
  level) is left blank. A size word or an amount phrase in a row's `unit` (`small`, `to
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

## The endpoints and API tokens

`views/api.py` holds the app's two JSON endpoints, its only views outside the
session login: `POST /recipes/api/recipes/` saves recipes, and
`GET /recipes/api/vocabulary/` answers with the lists the clipper loads (#160).
A browser extension's requests do not come from a page of this site, so a
session cookie plus CSRF token does not fit them; instead the client sends
`Authorization: Bearer <key>`:

- Both views are `@login_not_required` (they are in `PUBLIC_ROUTES`), and the
  save is `@csrf_exempt`. Neither looks at the session: a forged cross-site
  post carries the victim's cookie but not their key, so skipping CSRF is safe
  only because of that.
- 201 answers `{"recipes": [{"id", "name", "url", "renamed", "in_trash"}],
  "warnings": [...]}`, each `id` the recipe's UUID as text (#156); 400, 401
  (with `WWW-Authenticate: Bearer`), 405, 409, 413, 415 and 429 answer
  `{"error": "..."}`, and the refusals a client must tell apart add a `code`
  (#149): `token_expired`, `unsupported_media_type`, `rate_limited`,
  `too_many_recipes`, `too_many_new_names`. The body limit is Django's
  `DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB).
- Hardening (#149, `services/api_limits.py`): a save that is not
  `application/json` or `application/ld+json` is a 415. One may bring at most
  `API_MAX_RECIPES` recipes and make at most `API_MAX_NEW_NAMES` names the user
  lacks (ingredients and substitutes, units, tags, cuisines, each counted
  once; `new_name_count`), else a 413 and nothing is written, so a bad client
  cannot flood their suggestions. A key may send `API_REQUESTS_PER_MINUTE`
  requests a minute, and an address `API_FAILED_KEYS_PER_MINUTE` wrong or
  expired keys, before a 429 with `Retry-After` in seconds. The counts live in
  the default cache, per process, in windows of a minute from the first
  request in each. Each is a setting with an environment variable of the same
  name.
- `?id=<uuid>` (#158) names the id of the body's one recipe, made by the
  client when its draft starts, so a save sent twice makes one recipe. It must
  be a version 7 UUID, so ordering by id stays ordering by age, and the body
  must hold one recipe; otherwise 400. If the key's user already has a recipe
  with that id, live or in the trash, nothing is written and a 200 answers
  with that recipe in the same shape. Another user's id is a 409 that names
  nobody. The check and the write share one transaction, whose IMMEDIATE lock
  keeps two saves of one draft from both writing.
- The vocabulary (`services/vocabulary.py`) answers `{"user", "ingredients",
  "units", "cuisines", "tags", "limits"}` for the key's user. An ingredient or
  unit is `{"name", "spellings"}`: the canonical name and every other spelling
  the server accepts for it (its plural, its aliases and their plurals), each
  listed under the row `name_resolution` resolves it to, so the clipper looks
  names up and never inflects one. Lookups ignore case, and a unit's also
  ignore a trailing full stop. Ingredients, units and tags are the global ones
  plus the user's own, a name in both listed once as the global row; cuisines
  are the dotted paths of the global tree and the user's own nodes; `limits` is `recipe_document.FIELD_LENGTHS`, the length
  the reader allows each text field of a saved recipe (`tags`: each tag). One
  query per section, so its cost does not grow with the library. A new kind of
  data is a new section, not a new endpoint.
- `tests/api_examples/` holds one example of each request and reply, replayed
  by `tests/recipes/test_api_examples.py` against a small fixed library and
  matched exactly. The extension's tests read the same files, so a change to a
  reply shows up on both sides.
- `ApiToken` (`models/api_token.py`) stores only the SHA-256 digest of a key;
  the key is `nsh_` plus 43 random characters, shown once. A user may hold
  several; an inactive user's keys stop working, and `last_used_at` is noted on
  each use. A key expires (#149) on its own `expires_at`, if set, or once
  unused for `API_TOKEN_IDLE_DAYS` (90; 0 turns it off), counted from its last
  use or from when it was made. An expired key is still a 401, but with
  `code: token_expired` and `WWW-Authenticate: Bearer error="invalid_token"`,
  so the clipper can say to make a new one; an unknown key keeps the plain
  reply.
- Users manage their own keys on `/recipes/keys/` (#150, "API keys" on the
  Config page, `views/api_keys.py`): each is listed by name, when it was made
  and last used, and when it expires (`expires_on`: its own date or the end of
  its idle days, whichever is sooner), never by its key. Making one needs a
  name and may set a date (30 days, 90, a year); the key comes back once, in a
  full page sent `Cache-Control: no-store`, with a Copy button (`data-copy`
  in `app.js`). A user may hold `MAX_TOKENS_PER_USER` (10) keys
  (`make_own_token`). Revoke deletes the key behind `hx-confirm`; another
  user's key is a 404.
- For operators, `make manage ARGS="create_api_token <username> --name clipper [--days N]"`
  makes one for any user, with no cap, and prints the key, and its date if
  `--days` gave it one. Django admin lists every user's tokens, with their
  date and whether they have expired, and deletes them to revoke; it cannot
  add one, since it could not show the key.

For the extension: post from the background service worker, which with a host
permission for the server is not subject to CORS, so the server sends no CORS
headers. A content script would be.
