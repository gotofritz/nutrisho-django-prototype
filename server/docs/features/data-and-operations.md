# Data, storage and operations

## Key Models

- `Recipe` — core entity, keyed by a version 7 UUID (#156) so a client such as the clipper can name a recipe before it saves; steps, groups and rows keep integer ids. Owns name, description, cuisine, owner, servings (author's intended serving count; mandatory, NOT NULL, defaults to 1, constrained to `>= 1`); `plain_name` / `plain_description` are the tag-free name and description `save()` keeps current, for search and the per-owner name rule; `source_instance` (labelled Source) is free text, a book and page or a web address, and the recipe page links it only when it is a whole http(s) URL (`web_url` filter)
- `Ingredient`, `IngredientGroup`, `IngredientInRecipe` — ingredient hierarchy; `IngredientInRecipe.quantity` is stored as-is from source data (not normalized to per-serving). `Ingredient.owner` is NULL for the global list or the user a row is private to, and `ingredient_name` is unique case-insensitively among global rows and within each owner's private rows; `Ingredient.plural_name` is an optional display-only override for the pluralisation rule (blank derives it); `IngredientAlias` maps a case-insensitively unique `alias_name` to a global `canonical` ingredient (`CASCADE`), input-only; `IngredientInRecipe.ingredient` and `.substitute` are both `PROTECT`, and the optional substitute shows as `or X` after the name; `IngredientInRecipe.unit` is a `PROTECT` foreign key to `Unit` (canonical name, optional `plural_name`, `dimension` mass/volume/count, blank on a user's private unit; `Unit.owner` NULL for the global list, as for ingredients), with `UnitAlias` for input-only spellings and `legacy_unit` holding free text from before #67 (see `units.md`)
- `Recipe.deleted_at` is set while a recipe is in the trash (#75); see below
- `ApiToken` — a user's key for the JSON endpoints, stored as its SHA-256 digest; made and revoked by its user on the API keys page (#150), or by `create_api_token` and in admin; see `import-export.md`
- `IngredientChange` — one clean-up tool change to the shared ingredients, its steps in `events` (JSON) for Undo; see `ingredient-cleanup-tool.md`
- `Step` — ordered recipe steps; `step_title` is an optional heading, stored as `""` when absent and rendered underlined in front of the step text, followed by a colon
- Long prose (`Recipe.short_description`, `Step.step_text`) is a `TextField`, unlimited in the database; forms cap it at `PROSE_MAX_LENGTH` (4000), which step merge obeys too. `Ingredient.ingredient_name` and `.plural_name` share `INGREDIENT_NAME_MAX_LENGTH` (128)
- `Cuisine`, `Tag` — lookup/classification models; `Cuisine` is a node of the cuisine tree (`parent`, at most three levels), its name unique case-insensitively among its siblings, and `Cuisine.owner` is NULL for the global tree or the user a node is private to (#171); `Tag.owner` is NULL for a global tag or the user it is private to
- `Ingredient.family` and `.dietary_constraint` are staff data, set in the ingredient clean-up tool; the recipe page does not show them yet, and nothing rolls them up into a recipe-level label or filter
- Collections are plural (#79): `recipe.steps`, `recipe.ingredient_groups`, `group.items` (its `IngredientInRecipe` rows), `recipe.tags` and `tag.recipes`. The tag-recipe table is still `recipes_tag_recipe`, pinned with `db_table`, so the rename ran no SQL. A test calling a data migration from before 0028 passes it `pre_rename_apps` (`tests/recipes/conftest.py`), where `Tag.recipe` still has its old name
- Recipe ids became UUIDs in migration 0033 (#156). Django's `AlterField` copies an integer id into the new column as its decimal text, which no UUID matches, so the migration rewrites `recipes_recipe.id` and every `recipe_id` (steps, groups, `recipes_tag_recipe`) as 32-digit hex: recipe 10 became `00000000-0000-0000-0000-00000000000a`. Numbers sort as their hex does and new ids are version 7, so ordering by id is still ordering by age (export, search, trash). Going back, numbered recipes get their numbers again and newer ones the numbers after them, oldest first. Old numbered addresses (`/recipes/10/`) are gone; a redirect would only need that rule. `pre_rename_apps` lays 0033 over its 0027 models, so they read today's ids
- Dropped as unused in migration 0027 (#65): the `Source` model and `Recipe.source` (a recipe's source is `source_instance`), `Step.duration` and `Step.extra_info`. No code path ever wrote them; the migration stops, naming the column, if a database holds data in any of them

Empty text fields (`short_description`, `group_name`, `legacy_unit`,
`preparation`) are stored as `""`, never `NULL`.

## Data Flow

Browser → HTMX views → Django ORM → SQLite. The database is the only copy of the
data; the YAML seed files and their import/export commands were bootstrap
scaffolding and are gone (issue #27). A user can export their own recipes as a
Nutrisho JSON document and import one, or a page's schema.org JSON-LD, and the
recipe clipper posts recipes to a token-authenticated JSON endpoint (#78) and
loads the user's lists from another (#160); see
`import-export.md`.

`backup_db` (`make backup`) writes `docs/schema.sql` (committed, schema
only, deterministic order) and `docs/dump-<timestamp>.sql` (git-ignored, full
dump for restoring with `sqlite3`). SQLite only, like the rest of the app. The
dump is read inside one read transaction, so it is a consistent snapshot even
while the app writes (WAL lets those writes carry on).

`create_api_token <username> [--name ...] [--days N]` makes an API token and
prints its key once (#78); `--days` makes it expire (#149).

`delete_recipe --id <uuid>` removes recipes by primary key, as shown in the
recipe's address, trashed or not, for good.

`normalise_units` lists the legacy free-text units and what each becomes;
`--apply` moves them onto the unit vocabulary (see `units.md`).

`seed_demo` (`make seed`, #71) is development-only sample data: four recipes
for one user (`demo`, created as staff with a random password, unless
`--username` names an existing account) that cover duplicates of every class,
plurals, groups, substitutes, step titles, markup, tags and cuisines. It
refuses to run under `nutrisho.settings.prod`, adds only missing recipes on a
re-run, and `--reset` rebuilds them. The recipe list lives in the command
itself; when a feature adds a case worth reviewing, add it there.

## The recipe trash (#75)

Delete on the recipe page sets `Recipe.deleted_at` and leaves the row and its
steps, groups, ingredient rows and tags alone (`services/recipe_trash.py`).
`Recipe.objects.live()` and `.trashed()` split the two; every page, the search,
its cuisine and tag filters, prev/next and the tools' recipe columns read
`live()`, and `owned_recipe` 404s on a trashed recipe, so it cannot be opened or
edited. The name rule (`recipes_recipe_unique_plain_name_per_owner`) is a
partial constraint over live recipes, so a new recipe may take a trashed one's
name; restoring it then adds " Restored" (" Restored 2", …).

The delete view adds a message whose `extra_tags` hold the restore URL;
`partials/_page_regions.html` renders messages as toasts at the bottom of the
window, and one with a URL gets an Undo form posting there. `/recipes/trash/`
lists the owner's trashed recipes, newest first, each with Restore and Delete
for good (`purge`, behind `hx-confirm`). Restore opens the recipe. Nothing
empties the trash on a timer yet.

Bulk writes by cuisine or ingredient (the cuisine and ingredient tools) cover
trashed recipes too, since their rows still hold the references; that is what
keeps a restored recipe consistent.

## Concurrent writes

`settings/base.py` gives SQLite `transaction_mode: IMMEDIATE`, a 20 s busy
timeout, `journal_mode=WAL` and `synchronous=NORMAL` (issue #38). Write paths
read and then write inside `atomic()`, and `select_for_update()` is a no-op on
SQLite, so it is the IMMEDIATE write lock taken at `BEGIN` that serializes
them; with Django's default DEFERRED mode, overlapping writes fail with
`database is locked` instead of waiting. The database is three files
(`db.sqlite3`, `-wal`, `-shm`) that must be copied, moved and deleted together;
see the developer guide for the backup rules and the one-off switch of an
existing database. Tests use the same options on a temporary file database.

## Logging and health check

`settings/base.py` sends every log record to stderr through one handler on the
root logger (issue #43). The `django`, `recipes` and `nutrisho` loggers carry no
handlers of their own, only a level from `LOG_LEVEL` (default `INFO`), and
propagate to root; `django.security` is pinned at `WARNING`. Keep it that way:
a logger with `propagate: False` or its own handler would bypass the console
and pytest's `caplog`. Failed logins are logged by a `user_login_failed`
receiver in `recipes/signals.py`, connected in `RecipesConfig.ready()`.
Sentry is optional and initialised in `settings/prod.py` only when
`SENTRY_DSN` is set.

`GET /healthz` (`nutrisho/health.py`) is the one public route outside the
login pages: it is marked `login_not_required` so the login middleware lets it
through, is never cached, and answers 200 or 503 depending on `SELECT 1`.

## How far SQLite goes

Orders of magnitude for a small NVMe VPS, not benchmarks:

- Reads never block each other or the writer; tens of thousands of simple
  queries a second.
- Writes queue one at a time. A click here is a short transaction of about
  1 ms, so several hundred writes a second before anyone waits; 10 active users
  make about 2.
- A recipe is a few KB; 100,000 recipes is a few hundred MB.

Signals to move to Postgres, usually one of these rather than a user count:

1. A second app server, or the database on its own host. SQLite must sit on
   the app machine's local disk, never a network volume.
2. Writes queue: `database is locked` errors or rising p95 latency on saves
   despite IMMEDIATE and the 20 s timeout. Start planning at a sustained ~50
   writes a second.
3. Long write transactions (bulk imports, large merges) block every other
   writer for their whole duration.
4. Features or operations SQLite lacks: `pg_trgm` fuzzy search, read replicas,
   migrations without a table rebuild.

Until then, keep gunicorn to 2-4 workers. The move itself is mostly a data
copy: the code already uses `select_for_update` and portable constraints, but
Postgres enforces the `max_length` caps SQLite ignores.
