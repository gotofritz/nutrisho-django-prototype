
## Long-term evolution assessment (external architect, 2026-10-30)

Independent review of `main` at `20252bb`. Every "Verified" note was reproduced
on that commit, either with a throwaway test or a command against a scratch
database. Issues are ordered by priority within each band. IDs carry an `LTE-`
prefix so they cannot clash with numbering used elsewhere in this file.

### P1: broken or losing data today

#### LTE-01 Resolve ingredient names case-insensitively, in one place

**Problem.** `UniqueConstraint(Lower("ingredient_name"))` (migration 0013) is
enforced in the database, but every write path still looks names up with a
case-sensitive `get_or_create(ingredient_name=name)`:
`views/recipe_ingredients.py:165`, `forms/ingredient_forms.py:36,41,51` and
`management/commands/batch_load_yaml_recipes.py:325`. A case variant of an
existing name misses the lookup, tries to insert and hits the constraint.

- Verified: adding `Onion` to a recipe while `onion` exists returns **HTTP 500**.
- Verified: the committed corpus cannot be imported into a fresh database. It
  contains `Ginger`/`ginger`, `Sea salt`/`sea salt`, `Thai basil`/`thai basil`,
  `Cashew Nuts`/`cashew nuts` and `Sichuan pepper`/`sichuan pepper`, so
  `batch_load_yaml_recipes recipes_yaml/` aborts with
  `IntegrityError: UNIQUE constraint failed: index 'ingredient_name_ci_unique'`.
  That means `poe filldb` is broken on `main`.

**Proposal.** Add one service, `resolve_ingredient(name) -> Ingredient`, that
strips the name, looks it up with `ingredient_name__iexact`, and creates a row
only on a miss. Route the importer, `IngredientInRecipeForm`, and the create and
save views through it. This is also the hook plan 008 needs: alias resolution
then becomes one extra lookup inside the same function, not a change to four
call sites.

**Done when** both reproductions above have regression tests, and importing
`recipes_yaml/` into an empty database succeeds.

#### LTE-02 Make `poe clean` and `poe filldb` stop deleting committed migrations

**Problem.** `clean` runs `rm -f ./db.sqlite3 src/recipes/migrations/0*`, and
`filldb` then runs `makemigrations`. This deletes the 14 committed migrations,
including the data migration `0008_sanitize_yaml_filenames`, and replaces them
with one fresh `0001`. The working tree is left dirty. A developer who commits
afterwards ships a migration history that no existing database can apply.

Bootstrapping is also inconsistent:

- `addinitialuser` creates `gotofritz` with `User.objects.create(...)`, so the
  user has no usable password and cannot log in.
- `createsuperuser` creates a *different* user, `fritz`, with the password
  `fritz` and a personal email address, all hard-coded in `.poe.toml`.
- The recipes are imported for `gotofritz`, so the account that can log in owns
  no recipes.

**Proposal.**

- `clean` deletes only the database.
- `filldb` runs `migrate`, never `makemigrations`.
- Merge the two user tasks into one `bootstrap` that creates a single owner
  whose username and password come from the environment (`.env.example`
  documents them), using `create_user` or `create_superuser`.
- Add a CI check, `makemigrations --check --dry-run`, so model changes without a
  migration are caught.

#### LTE-03 Make "Duplicate recipe" copy every field, including step titles

**Problem.** `recipe_duplicate` (`views/recipe_crud.py:176-181`) copies `Step`
field by field and was not updated when `step_title` arrived (migration 0015).
Verified: duplicating a recipe whose step is titled `Ragu` gives a copy whose
title is `''`. Every new field on `Step`, `IngredientGroup` or
`IngredientInRecipe` will be silently dropped the same way.

**Proposal.** Copy rows generically from `_meta.concrete_fields`, excluding the
pk and the parent FK. Add a test that walks those same fields, so the next new
column fails a test instead of disappearing.

#### LTE-04 Align field lengths with the data, and validate them on import

**Problem.** SQLite does not enforce `VARCHAR(n)`, so the corpus already stores
values longer than the model allows:

- 3 steps over `Step.step_text` `max_length=512` (`Borscht` has 656 characters).
- 6 descriptions over `short_description` 512.
- 1 ingredient name of 72 characters, over 64.

These recipes import, but the inline editor's `ModelForm` rejects them, so a
user cannot save an edit to one of those steps without cutting it down first.
Any move to PostgreSQL would also fail on import. The importer validates only
step-title length.

**Proposal.**

- Make `step_text` and `short_description` `TextField`s, since they are prose
  and have no natural limit.
- Decide on a real limit for `ingredient_name`.
- Have the importer validate every field against the model, either with
  `full_clean()` or a schema (see LTE-08), before the write phase, as it already
  does for quantities and servings.
- While touching `Ingredient`, drop `unique=True` from `ingredient_name`. The
  case-insensitive constraint already covers it.

#### LTE-05 Cut the test suite from 7 minutes to seconds with a fast test password hasher

**Problem.** `uv run poe test` takes about 7 minutes for 823 tests (verified:
`823 passed in 421.74s`). Most of that is PBKDF2 hashing in `create_user`, which
runs per test. The pre-commit hook runs the whole `qa` sequence on every commit
that touches Python, so this cost lands on every commit.

**Proposal.** In `nutrisho/settings/test.py`, add
`PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]`.
Verified on `test_views_steps.py`: 32.2s drops to 1.7s, about 19× faster.
This is a one-line change and the cheapest high-value item in this list.

### P2: architecture that will hurt as the app grows

#### LTE-06 Scale recipes at display time instead of rewriting stored quantities

**Problem.** `recipe_scale` overwrites every `IngredientInRecipe.quantity`
(rounded to 0.01) and `Recipe.servings` (rounded to a whole number). This has
four consequences:

- **It is lossy.** Scaling by ⅓ and then by 3 does not restore the original.
- **The ratio drifts.** `servings=1 × 1.5` stores 2 servings while the
  quantities are ×1.5.
- **The source of truth changes.** Viewing "for 6" changes what gets exported
  to YAML.
- **Pluralisation inherits it.** `display_ingredient_name`'s docstring already
  has to explain that it guards against "2 onion" because of persisted scaling.

**Proposal.** Treat scaling as presentation. The recipe page accepts a target
serving count (`?servings=6`, kept in the URL so it can be bookmarked and
printed), and the template computes the displayed quantities from the stored
ones. If keeping a scaled version is wanted, offer "Save as scaled copy", which
reuses duplicate (LTE-03). Stored quantities then always match the source.

#### LTE-07 Define the YAML ↔ database contract: source of truth, upsert, backups

**Problem.** There are two stores and no rule for which one wins.

- The importer only ever inserts.
- The documented way to fix a recipe is *export → edit YAML → `delete_recipe`
  → re-import*. That gives the recipe a new id, which breaks bookmarked URLs,
  and silently drops anything YAML cannot carry (export already lists
  `source`, `duration`, `extra_info` and `substitute` as lossy).
- Edits made in the UI live only in `db.sqlite3`, which is untracked and has
  no backup.
- `recipes_yaml/` in git drifts away from the database until someone
  remembers to export.

**Proposal.**

1. Declare the database the source of truth, and YAML the
   interchange and backup format.
2. Make import an upsert keyed on `(owner, yaml_filename)`, falling back to
   `(owner, recipe_name)`, behind `--update`, so re-importing an edited file
   keeps the recipe's id.
3. Add a `poe backup` task: export plus `dumpdata`.
4. Add a CI round-trip test: import the corpus, export it, and expect
   byte-identical files. This would have caught LTE-01.

#### LTE-08 Give the YAML format a typed, versioned schema

**Problem.** The YAML shape is defined only by two hand-written modules: the
importer's `_validate_payload` and `_normalize_steps`, and the exporter's dict
builder. Steps can be either a bare string or a `{title, text}` mapping;
`group` and `ingredient` can be either a list or a scalar; and there is no
version field. Every format change (servings, step titles) has meant editing
both ends in step.

**Proposal.** Define one Pydantic model of a recipe file with a
`schema_version` field. The importer parses into it, and the exporter
serialises from it. Plan 005 already names Pydantic for exactly this.
Validation errors then report the file and the field for free, and LTE-04's
length checks become declarative.

#### LTE-09 Surface the schema fields the UI hides, or remove them

**Problem.** Several modelled fields have no way in or out through the UI.

| Field or model | Imported | Exported | Shown on recipe page | Editable |
|---|---|---|---|---|
| `Tag` | yes | yes | no | no |
| `Cuisine` | yes | yes | no | metadata form only |
| `Source` (model) | no | flagged lossy | no | admin only |
| `IngredientInRecipe.substitute` | no | flagged lossy | no | no |
| `Step.duration`, `Step.extra_info` | no | flagged lossy | no | no |

Unused columns cost a migration and a code path every time the model changes,
and tags and cuisine are imported but cannot be seen.

**Proposal.** Decide field by field. The suggested starting point:

- **Show:** tags, cuisine, `source_instance`, and `substitute` (rendered as
  "or X").
- **Make editable:** tags.
- **Drop in a migration:** `Source`, `duration` and `extra_info`, unless there
  is a concrete plan for them.

#### LTE-10 Let users search, filter and page the recipe list

**Problem.** `/recipes/` renders all 273 recipes in one unpaginated list, with
no search and no filter. For a recipe manager the core question is "what can I
make with aubergine", or "show me Sichuan dishes". The data to answer it exists
(ingredients, cuisine, tags), but nothing exposes it. Prev/next on the detail
page also walks by id ascending while the list is sorted newest first, so the
two orders disagree.

**Proposal.**

- Add an HTMX active-search box over recipe name and ingredient names (the same
  pattern the ingredient tool uses).
- Add filter chips for cuisine and tag (depends on LTE-09) and paginate.
- Carry the current list query into the detail page so prev/next follows the
  list.

#### LTE-11 Restrict the global ingredient tool to staff (or commit to single-user)

**Problem.** Recipes are owner-scoped everywhere, which implies more than one
user. But `Ingredient`, `Tag` and `Cuisine` are global, and `/recipes/ingredients/manage/`
requires only a login. Any authenticated user can rename, merge or delete
ingredients used in other owners' recipes. `initial-context.md` acknowledges
that the tool reaches recipes the user cannot see.

**Proposal.** Pick a direction.

- **Multi-user:** gate the `manage/` routes behind `is_staff`, or the
  `recipes.change_ingredient` and `recipes.delete_ingredient` permissions, and
  test that an ordinary user gets 403.
- **Single-user:** say so in `initial-context.md` and stop paying for owner
  scoping.

Staying half-way is the risky option.

#### LTE-12 Make login enforcement secure by default with `LoginRequiredMiddleware`

**Problem.** Authentication is opt-in per route. Each of the 50+ entries in
`recipes/urls.py` is wrapped by hand in `_lr()`, `home` also carries
`@login_required`, and `nutrisho/urls.py` wraps `_root` separately. A new route
that misses the wrapper reaches its view anonymously, and the view's
`owner=request.user` query then fails as a 500 rather than a redirect.

**Proposal.** Use Django's `LoginRequiredMiddleware` (5.1+), subclassed so
that `handle_no_permission` keeps the current `HX-Redirect` behaviour from
`views/_auth.py`, and mark the auth views `@login_not_required`. Then delete
`_lr()`. Add one test that iterates every URL pattern and asserts an anonymous
request never gets a 200 or a 500.

#### LTE-13 Normalise units before building anything on quantities

**Problem.** `unit` is free text, and the corpus shows it:

| Kind of problem | Values in the corpus (count) |
|---|---|
| Spelling variants of one unit | `Tbsp` 268, `tbsp` 226, `tbs` 7, `tbso` 2 |
| Singular and plural both stored | `clove`/`cloves`, `cup`/`cups`, `sprig`/`sprigs` |
| Case variants | `l`/`L` |
| Not units at all | `small`, `medium`, `large`, `to taste` |

Concrete effects today:

- The pluralisation gate treats any non-empty unit as a measure, so the page
  renders "2 small onion".
- Scaling multiplies quantities that sit next to "to taste".

Longer term, shopping lists, unit conversion, and the nutrition features the
name *Nutrisho* suggests all need canonical units.

**Proposal.** Introduce a canonical unit vocabulary with aliases (the same
shape as plan 008's ingredient aliases), resolve units on input, and migrate
existing values with a reviewed management command, as was done for
ingredients. Size words move to `preparation`. Pluralise units too, so the page
shows "1 clove" and "2 cloves" from one stored value.

### P3: tooling, quality and hygiene

#### LTE-14 Prune runtime dependencies

**Problem.** `[project].dependencies` ships three packages that do not belong
at runtime:

- `google-genai` is imported nowhere.
- `xmltodict` is used only by the one-off `scripts/import.py`, which reads a
  hard-coded `/Library/WebServer/...` path.
- `django-debug-toolbar` is loaded only by `settings/dev.py`.

`scripts/sql_to_edit_recipes_hack/` hard-codes
`/Users/fritz/...` and deletes rows by hand-written SQL. It predates
`delete_recipe` and the inline editor, both of which replace it.

**Proposal.**

- Remove `google-genai`.
- Move `django-debug-toolbar` to the `dev` group.
- Archive `scripts/import.py` and the SQL hacks, or delete them from the tree
  (git keeps the history), and drop `xmltodict` with them.

#### LTE-15 Harden CI: locked installs, pinned uv, dependency updates

**Problem.**

- **Lockfile drift is not caught.** CI runs `uv sync --all-groups`, not
  `--locked`, so a `pyproject.toml` change with a stale `uv.lock` passes. A
  local `uv sync` with a different uv version also rewrote the lock header
  during this review.
- **uv is unpinned.** `setup-uv` installs whatever version is current.
- **Nothing tracks updates.** There is no Dependabot or Renovate for Python,
  pnpm, GitHub Actions or the pre-commit hook revisions, on a project pinned to
  Python 3.14 and Django 6.0, both of which move quickly.

**Proposal.**

- Run `uv sync --locked --all-groups`.
- Pin `version:` in `setup-uv`.
- Add a `.github/dependabot.yml` covering `uv`, `npm` and `github-actions`, and
  a monthly `pre-commit autoupdate` job.
- Add `manage.py makemigrations --check` (see LTE-02).

#### LTE-16 Add a small browser test suite for the HTMX flows

**Problem.** All 823 tests use Django's test client and assert on the HTML
returned. But the UI's correctness depends on things only a browser exercises:

- `hx-include` selectors.
- Out-of-band swaps.
- `HX-Retarget` handling.
- The inline JavaScript in `base.html` (reassign panel, textarea sizing).
- The `indeterminate` checkbox.

`initial-context.md` already documents pitfalls of exactly this kind ("pointing
it at a container element sends nothing"), and none of them can fail a
server-side test.

**Proposal.** Add `pytest-playwright` with `live_server`, plus a handful of
smoke flows:

- Add, edit and reorder a step.
- Add an ingredient to a group.
- Merge two ingredients in the clean-up tool.
- Scale a recipe.

Mark them `e2e`, run them in CI, and keep them out of the pre-commit hook.

#### LTE-17 Fix the step HTML sanitizer: trailing text lost, open tags leak

**Problem.** `_StepHtmlSanitizer` never calls `HTMLParser.close()`, and it does
not track which tags are open. Verified:

- `safe_step_html("heat <")` returns `'heat '`.
- `"end with <!"` returns `'end with '`. The trailing text is silently dropped.
- `"A <b>bold"` returns `'A <b>bold'` with no closing tag, so everything after
  that step on the page renders bold.

**Proposal.** Call `close()` after `feed()`. Keep a stack of open allowed tags,
emit their closing tags at the end, and ignore stray closing tags with no
matching opener. Add tests for each case.

#### LTE-18 Pick one styling approach and move inline JS into a static file

**Problem.** The frontend mixes two styling systems: Tailwind v4, used for
about 26 utility classes (mostly in the ingredient tool), and 370 lines of
hand-written `style.css` for everything else. Tailwind is the only reason the
project needs Node and pnpm in CI, pre-commit and local setup. Meanwhile
`base.html` carries a growing block of inline JavaScript that cannot be linted
or cached, and the page loads Google Fonts from a third-party CDN.

**Proposal.**

- Either move the remaining styles to Tailwind, or convert the 26 utilities to
  plain CSS and drop the Node toolchain. The second option is cheaper and fits
  a server-rendered HTMX app.
- Move the inline scripts into `static/js/app.js`.
- Self-host the two fonts.
- Set `<html lang="en">`. It is currently `lang=""`.

#### LTE-19 Fix doc drift and keep `initial-context.md` focused on architecture

**Problem.**

- `docs/developer-guide.md` still prescribes `feature/<name>` branches, which
  `AGENTS.md` retired.
- `README.md` and the developer guide use a bare `python manage.py`, which
  `AGENTS.md` forbids.
- Plans 005 and 006 have been "Draft" since May. Plan 005 asks to review
  "FloatField vs DecimalField", but quantity has been a `DecimalField` for a
  long time.
- `initial-context.md`, the document every contributor and agent must read
  first, has grown into a feature changelog. It includes Miller-column UI
  behaviour, the panel-closing rules for saves, and the `HX-Retarget` details.
  That makes the architecture hard to find and the file expensive to read.

**Proposal.**

- Fix the branch and command examples.
- Re-scope or archive plans 005 and 006.
- Move feature-level notes into `docs/features/<feature>.md`.
- Keep `initial-context.md` to the stack, boundaries, core patterns and
  constraints, at no more than about 100 lines.
