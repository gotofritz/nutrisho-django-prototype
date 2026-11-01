# Plan 01: Assessment backlog (2026-10-30)

## Status: Triaged, tracked in GitHub issues

Fourteen independent reviews (architecture, security, SRE, QA, performance,
developer experience, product/UX, open-source maintenance, technical debt,
dependencies, agent readiness, correctness, long-term evolution and
accessibility) were run against the branch on 2026-10-30. Together they raised
about 150 findings, most of them reported by several reviewers. This plan
merges them into 49 items, prioritises them and links each to its GitHub
issue. The raw reports are kept in
[`docs/reviews/2026-10-30-assessment-reports.md`](../reviews/2026-10-30-assessment-reports.md);
every item lists the report IDs it absorbs (`COR` is the unprefixed
day-to-day correctness review).

## How to read it

| Priority | Label | Meaning |
|---|---|---|
| **A** | `P1` | Broken or losing data today, or a blocker for the VPS move. |
| **B** | `P2` | Important: hardening, visible bugs, guard-rails. Before or soon after the VPS move. |
| **C** | `P3` | Worth doing; cheap hygiene or quality work with no deadline pressure. |
| **One day** | `Backlog` | Good ideas that wait for a reason (a feature, growth, the redesign). |

**Redesign.** A redesign is planned (see the UX report's "If the app is
redesigned"). Items it affects also carry the `redesign` label and one of:

- **Design-led:** solve it in the redesign; patching the current UI first is
  throwaway work.
- **Split:** the design decides the interaction or look, but the backend or
  behavioural part is needed regardless and can land now.

Suggested design brief from the UX review: the **cooking view on a phone or
tablet** is the primary screen and editing a secondary mode; include print,
since `print.css` targets the current card layout. Accessibility items B16,
B17 and C13 should be acceptance criteria for the redesign.

Existing issues are reused, not duplicated: search lives in **#32**, reusable
steps in **#19** (B4 and A2 should land before it), and aliases (C5) re-file
the closed **#14**.

## Summary

| ID | Item | Issue | Redesign |
|---|---|---|---|
| A1 | Resolve ingredient and cuisine names case-insensitively | #34 | |
| A2 | Make "Duplicate recipe" copy every field, including step titles | #35 | |
| A3 | Scale recipes at display time instead of rewriting quantities | #36 | Split |
| A4 | Tell the user when an HTMX save fails | #37 | Split |
| A5 | Configure SQLite for concurrent writes (WAL + IMMEDIATE) | #38 | |
| A6 | Replace the user bootstrap commands; remove the hard-coded password | #39 | |
| A7 | Remove `google-genai`, move the debug toolbar to dev, clear lockfile CVEs | #40 | |
| A8 | Harden production security settings | #41 | |
| A9 | Serve static files in production | #42 | |
| A10 | Make production errors and outages visible | #43 | |
| A11 | Make backups automatic, consistent, off-box and restore-tested | #44 | |
| A12 | Add a deployment recipe and runbook for the VPS | #45 | |
| B1 | Restrict the ingredient manager to staff, or commit to single-user | #46 | |
| B2 | Rate-limit the login and admin pages | #47 | |
| B3 | Require login by default and test every route for auth and ownership | #48 | |
| B4 | Make long prose fields `TextField`s | #49 | |
| B5 | Stop the HTML sanitiser truncating text after a stray `<` | #50 | |
| B6 | Confirm before deleting a non-empty ingredient group | #51 | |
| B7 | Self-host the web fonts | #52 | Split |
| B8 | Enforce migrations, `schema.sql` and other cheap invariants in QA/CI | #53 | |
| B9 | Harden the CI workflow | #54 | |
| B10 | Automate dependency updates and vulnerability scanning | #55 | |
| B11 | Delete dead scripts and legacy code | #56 | |
| B12 | Make the documented `manage.py` commands work on a fresh checkout | #57 | |
| B13 | Search, filter and paginate the recipe list | #32 | Design-led |
| B14 | Responsive layout with a read/cook mode | #58 | Design-led |
| B15 | Add log-out and a proper login page | #59 | Design-led |
| B16 | Make every control keyboard-reachable and named | #60 | Split |
| B17 | Manage focus and announce changes after HTMX swaps | #61 | Split |
| C1 | Move inline JavaScript to static files and add a CSP | #62 | Split |
| C2 | Add browser smoke tests for the HTMX flows | #63 | Split |
| C3 | Fix N+1 queries when HTMX endpoints re-render | #64 | |
| C4 | Show or drop the schema fields the UI hides | #65 | Split |
| C5 | Resolve aliases and plurals on ingredient input | #66 | |
| C6 | Normalise units | #67 | |
| C7 | Tidy the poe test and QA tasks | #68 | |
| C8 | Fix documentation drift | #69 | |
| C9 | Tidy the committed Claude Code configuration | #70 | |
| C10 | Add a demo-data seed command | #71 | |
| C11 | Cut versioned releases with a changelog | #72 | |
| C12 | Upgrade off Django 6.0 before its support ends | #73 | |
| C13 | Fix page structure: landmarks, headings, language, contrast | #74 | Split |
| D1 | Soft-delete recipes with undo | #75 | Split |
| D2 | Pick one styling system | #76 | Design-led |
| D3 | Move domain logic into services and slim the view layer | #77 | |
| D4 | Import recipes from JSON-LD or pasted text | #78 | |
| D5 | Rename reverse accessors to plurals | #79 | |
| D6 | Replace the ingredient datalist with an autocomplete endpoint | #80 | |
| D7 | Squash migrations 0001–0016 | #81 | |

---

## A — P1

### A1 · Resolve ingredient and cuisine names case-insensitively

Issue: #34 · Sources: LTE-01, QA-2, ARCH-1, COR (case crash, cuisine case)

**Problem.** Migration 0013 made `ingredient_name` unique case-insensitively,
but the recipe editor resolves typed names with a case-sensitive
`get_or_create(ingredient_name=name)` in three places
(`IngredientInRecipeForm.save`, `resolve_pending_ingredient`,
`recipe_ingredient_create`). With `onion` stored, adding or saving `Onion`
returns **HTTP 500** (`IntegrityError`). Phones auto-capitalise, so this is
common. `Cuisine` uses the same pattern without a constraint, so `Italian` and
`italian` silently become two cuisines.

**Fix.** One service, `resolve_ingredient(name) -> Ingredient`: strip, look up
with `ingredient_name__iexact`, create only on a miss, keep the stored
spelling. Route all three call sites through it. Do the same for cuisine, and
add a `Lower("cuisine")` unique constraint once existing duplicates are merged.
This is the function plan 008 (C5) extends with aliases.

**Done when** create and save with `Onion` reuse `onion` (regression tests per
endpoint), the same holds for cuisine, and no `Ingredient.objects.get_or_create`
remains outside the service.

### A2 · Make "Duplicate recipe" copy every field, including step titles

Issue: #35 · Sources: LTE-02, UX-2, ARCH-3, LT-1, PERF-3, COR (duplicate)

**Problem.** `recipe_duplicate` copies `Step` rows field by field and was not
updated when `step_title` arrived (migration 0015): every duplicate loses its
step headings (reproduced by five reviewers). Any future column on `Step`,
`IngredientGroup` or `IngredientInRecipe` will be dropped the same way. It is
also slow: 414 queries for a 6×20-ingredient, 30-step recipe, one INSERT per
row plus two lazy FK loads per ingredient, all under SQLite's write lock.

**Fix.** Move duplication into a service that copies rows generically from
`_meta.concrete_fields` (clear pk, reassign parent FK), copies FKs by id
(`ingredient_id`, `substitute_id`) and uses `bulk_create` per level.

**Done when** a test walks every concrete field of the three child models and
asserts it survives a duplicate (so the next new column fails CI), and the
query count no longer grows with recipe size. Land before #19.

### A3 · Scale recipes at display time instead of rewriting quantities

Issue: #36 · Sources: LTE-05, QA-4, UX-1, ARCH-5, LT-2, COR (scaling) · Redesign: **Split**

**Problem.** `recipe_scale` multiplies and **persists** every quantity
(rounded to 0.01) and servings (rounded to an integer, floor 1). The database
is the only copy of a recipe, so: scaling cannot be undone (÷3 then ×3 turns
`1` into `0.99`); small quantities become `0.00` for good; servings and
quantities drift apart (3 servings × 0.5 stores 2 servings with amounts for
1.5; `test_scale_down_sub_half_result_clamps_to_1` pins this as correct). The
panel asks for a factor, so 4→6 servings means computing 1.5 by hand.

**Fix.** Treat scaling as presentation: the recipe page takes a target serving
count (`?servings=6`, bookmarkable and printable), computes displayed
quantities from the stored ones and offers "reset". If a permanent version is
wanted, offer "Save as scaled copy" (reuses A2). Remove the persisting path,
or compute it from the original values with a warning.

**Redesign.** The design decides how target servings are asked for and how it
shows that scaling is temporary; making scaling non-destructive is backend work
needed either way and should land now.

### A4 · Tell the user when an HTMX save fails

Issue: #37 · Sources: QA-5, UX-3, COR (silent errors) · Redesign: **Split**

**Problem.** `htmx-config` in `base.html` maps every non-2xx/422 response to
`swap: false, error: true`, and nothing listens for `htmx:responseError`,
`htmx:sendError` or `htmx:timeout`. With `DEBUG=False` a 403, 404, 500 or
dropped connection does nothing visible: the user thinks the edit saved. On a
VPS this will happen (network blips, restarts, CSRF token rotated by logging in
on another tab, recipe deleted in another tab).

**Fix.** One global listener that shows a dismissible "Your change was not
saved" banner (with a reload hint on 403) and keeps the edit form open so typed
text is not lost. Cover it in the browser tests (C2).

**Redesign.** The design defines the banner and saving states; the handler is
needed regardless and should land now with a minimal banner.

### A5 · Configure SQLite for concurrent writes (WAL + IMMEDIATE)

Issue: #38 · Sources: QA-1, PERF-1, PR-5, ARCH-4, ARCH-12

**Problem.** SQLite runs with Django's defaults (rollback journal, `DEFERRED`
transactions). Write paths read first and write second (`select_for_update` is
a no-op on SQLite), so two overlapping requests fail the read→write lock
upgrade **immediately**, ignoring the busy timeout. Reproduced: 8 threads × 15
step moves gave **57/120 HTTP 500** (`database is locked`); with the fix, 0 in
360. Any multi-worker server, or a double-click, hits this. The comment in
`utils/sequencing.py` assumes serialisation that only `IMMEDIATE` provides.

**Fix.** When the engine is SQLite, set `OPTIONS` to
`transaction_mode: "IMMEDIATE"`, `timeout: 20`, and `init_command` with
`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`. Note the `-wal`/`-shm`
files in the backup procedure (A11). Keep ARCH-12's capacity notes (signals to
move to Postgres) in `docs/initial-context.md`.

**Done when** a test asserts the options, and a file-backed concurrency test
(`transactional_db` or `live_server` with a thread pool) fires concurrent moves
and sees no 500s and a contiguous `index_in_sequence`.

### A6 · Replace the user bootstrap commands; remove the hard-coded password

Issue: #39 · Sources: LTE-04, SEC-01, PR-7, DX-1, OSM-6, OSM-7, AR-6, TD-2

**Problem.** The developer guide's setup runs `addinitialuser`, which calls
`User.objects.create(username="gotofritz")` with no password, so nobody can log
in (its help text says "Adds a single recipe"; it has no test). The working
path, `poe createsuperuser`, is undocumented and hard-codes user `fritz`,
password `fritz` and a personal email in `.poe.toml`. Run on the VPS out of
habit, it plants a superuser with a guessable password behind a public
`/admin/`: a full takeover.

**Fix.** Delete `addinitialuser` and the hard-coded credentials. One
`poe bootstrap` (or `createsuperuser`) task that creates a single owner via
`create_superuser`, reading `DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD` from the
environment with no defaults (placeholders in `.env.example`) or prompting, and
doing nothing if the user exists. Document it in *First-time setup*. Rotate the
password of any account created with `fritz`.

### A7 · Remove `google-genai`, move the debug toolbar to dev, clear lockfile CVEs

Issue: #40 · Sources: LTE-12, SEC-06, PR-10, DX-7, OSM-1, OSM-2, TD-1, DEP-1, DEP-2, DEP-5

**Problem.** `google-genai` is a runtime dependency nothing imports. About 25
of the 32 runtime packages exist only because of it, including the only route
to a flagged `certifi` (PYSEC-2026-4320). `django-debug-toolbar` ships as a
runtime dependency although only `settings/dev.py` uses it (and is two majors
behind). Dev lockfile entries `filelock` and `virtualenv`, and the build-time
`source-map-js`, also have published advisories.

**Fix.** `uv remove google-genai`; move `django-debug-toolbar` to the `dev`
group, lift its `~=6.1` cap, and guard `urls.py` with
`"debug_toolbar" in settings.INSTALLED_APPS` instead of `settings.DEBUG`.
Refresh `filelock`/`virtualenv` (`uv lock --upgrade-package …`) and
`pnpm update`. `uv sync --no-dev` should then install only Django,
`django-environ` and `django-htmx`.

### A8 · Harden production security settings

Issue: #41 · Sources: SEC-02, SEC-03, PR-2, ARCH-7, PR-9

**Problem.** `prod.py` only sets `DEBUG = False`. `check --deploy` reports
W004, W008, W012 and W016. Behind a TLS-terminating proxy, without
`SECURE_PROXY_SSL_HEADER` Django sees HTTP, so **every POST fails CSRF** (or
`SECURE_SSL_REDIRECT` loops). `CSRF_TRUSTED_ORIGINS` is unset. A real
`SECRET_KEY` sits in git history, `dev.py` falls back to a known key, and
`prod.py` accepts any key, so a forged session could log in as anyone.

**Fix.** In `prod.py`, env-driven: `SECURE_PROXY_SSL_HEADER`,
`CSRF_TRUSTED_ORIGINS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` (start at ~3600). Raise
`ImproperlyConfigured` when the key is under 50 characters, starts with
`django-insecure` or matches a known placeholder. Generate a fresh key on the
server.

**Done when** CI runs `manage.py check --deploy --fail-level WARNING` with prod
settings and a random key, and it passes.

### A9 · Serve static files in production

Issue: #42 · Sources: PR-1, SEC-07, ARCH-7, PERF-5, PR-9

**Problem.** There is no `STATIC_ROOT`, so `collectstatic` fails, and with
`DEBUG=False` nothing serves `/static/`: no CSS and **no HTMX**, so the app is
unusable, not just unstyled. Filenames are unhashed, so assets can't be cached
long-term. `output.css` is a git-ignored Tailwind build artifact.

**Fix.** `STATIC_ROOT` from env (default `BASE_DIR / "staticfiles"`,
git-ignored); WhiteNoise with `CompressedManifestStaticFilesStorage` (or the
proxy serving `STATIC_ROOT` with `Cache-Control: immutable`). Build CSS in CI
and ship it with the release so the server needs no Node toolchain.

**Done when** a test or CI step runs `collectstatic --noinput` under prod
settings.

### A10 · Make production errors and outages visible

Issue: #43 · Sources: PR-6, SEC-07, ARCH-7, PR-12, SEC-13

**Problem.** There is no `LOGGING` and no `ADMINS`, so with `DEBUG=False` a 500,
a CSRF failure or a `django.security` event leaves no trace anywhere. There is
nothing for an uptime monitor or the deploy smoke check to hit (`/` redirects
to login).

**Fix.** A `LOGGING` config sending `django`, `django.security` and `recipes`
to stderr (journald collects it), level from `LOG_LEVEL`, including failed
logins. Optional Sentry via `SENTRY_DSN`, initialised only when set. An
unauthenticated `GET /healthz` that runs `SELECT 1` and returns 200/503,
excluded from login enforcement. Point a free external monitor at it, and a
healthchecks.io ping at the backup timer (A11).

### A11 · Make backups automatic, consistent, off-box and restore-tested

Issue: #44 · Sources: LTE-06, SEC-08, PR-4, QA-8, ARCH-8, PERF-1

**Problem.** Since #27 the database is the only copy of the data, and
`backup_db` is manual, writes into `docs/` inside the checkout (one `git add -f`
from a commit), with the default umask (often world-readable), builds the whole
dump in memory, and uses `iterdump()`, which is not a consistent snapshot while
the app writes. Dumps include `auth_user` hashes and live `django_session` keys
(a ready-made login). No test restores one.

**Fix.** Keep `--schema-only` as it is for `docs/schema.sql`. For data, take a
consistent copy with `sqlite3.Connection.backup()` or `VACUUM INTO`, into
`BACKUP_DIR` (env, outside the repo), mode `0600`, skipping sessions in any SQL
dump; keep the last *N*. Schedule it (systemd timer on the VPS) and ship copies
off the box encrypted (restic/rclone, or Litestream for continuous
replication).

**Done when** a test backs up a populated database, restores it into a fresh
one and compares row counts per table, and the restore procedure is documented.

### A12 · Add a deployment recipe and runbook for the VPS

Issue: #45 · Sources: PR-3, SEC-07, PR-7, SEC-13, PERF-4, ARCH-4, ARCH-7

**Problem.** There is no WSGI server, no service unit, no proxy config and no
deploy doc, so the easiest way online is `runserver` with dev settings.
`.poe.toml`'s top-level `[env]` forces `nutrisho.settings.dev` on every task,
so `poe migrate`/`poe backup` on the server would run with `DEBUG=True`. The
SQLite file defaults to `BASE_DIR/db.sqlite3`, inside the checkout, where a
reclone or `git clean -fdx` deletes it. Nothing is compressed (114 KB per
ingredient-edit click at 2,000 ingredients).

**Fix.**

- Add `gunicorn` (2–4 workers) bound to localhost or a unix socket; commit
  `deploy/nutrisho.service` (own user, `ProtectSystem=strict`,
  `NoNewPrivileges`, `ReadWritePaths` limited to DB and backups) and
  `deploy/Caddyfile` (automatic TLS, gzip/zstd for HTML/CSS/JS, sets
  `X-Forwarded-Proto`).
- Have poe set `DJANGO_SETTINGS_MODULE` only when unset.
- `DATABASE_URL` outside the checkout (e.g. `/var/lib/nutrisho/db.sqlite3`);
  secrets in a root-owned `0600` `EnvironmentFile`.
- `docs/deployment.md`: `uv python install 3.14`, `uv sync --frozen --no-dev`,
  `migrate`, `collectstatic`, restart, smoke-check `/healthz`; VPS baseline (SSH
  keys only, firewall 22/80/443, unattended-upgrades).
- Update the "no production settings" constraint in `docs/initial-context.md`.

---

## B — P2

### B1 · Restrict the ingredient manager to staff, or commit to single-user

Issue: #46 · Sources: LTE-09, SEC-05, PR-13, QA-9, ARCH-2, LT-3

**Problem.** Recipes are owner-scoped, but `Ingredient`, `Tag`, `Cuisine` and
`Source` are global, and `/recipes/ingredients/manage/` requires only a login.
Any second account can rename, merge or delete ingredients in everyone's
recipes. Fine with one account; broken access control with two. Plan 008's
aliases and any importer will deepen whichever model is chosen.

**Fix.** Decide and write it in `docs/initial-context.md`. Either way, gate the
manager routes behind `is_staff` or `recipes.change_ingredient` /
`delete_ingredient` with an HTMX-aware 403, tested with the `other_user`
fixture on every mutating route. If multi-user is a goal, plan per-owner
vocabularies before aliases land.

### B2 · Rate-limit the login and admin pages

Issue: #47 · Sources: SEC-04, PR-8

**Problem.** `/accounts/login/` and `/admin/login/` accept unlimited guesses
and failures are not logged. On a public IP this is the most likely attack.

**Fix.** `django-axes` (per user+IP lockout), or proxy rate limiting plus a
fail2ban jail on the auth log (needs A10's logging). Move admin to an
env-configured path or restrict it to an allowlist/VPN.

### B3 · Require login by default and test every route for auth and ownership

Issue: #48 · Sources: LTE-10, TD-4, ARCH-6

**Problem.** Each of ~55 routes is wrapped in `_lr()` by hand (`home` is
wrapped twice), and recipe ownership is a hand-written
`get_object_or_404(..., owner=request.user)` repeated 38 times. A route that
misses either ships public or as an IDOR; `test_views_ownership.py` covers 16
of ~40 recipe-scoped endpoints.

**Fix.** Subclass Django's `LoginRequiredMiddleware` so
`handle_no_permission` keeps the `HX-Redirect` behaviour, mark the auth views
and `/healthz` `@login_not_required`, delete `_lr()`. Add a small
`owned_recipe(request, recipe_id)` helper. One parametrised test walks the
URLconf and asserts anonymous requests redirect (never 200/500) and another
user gets 404 on every route with a `recipe_id`.

### B4 · Make long prose fields `TextField`s

Issue: #49 · Sources: LTE-03, ARCH-10, ARCH-12

**Problem.** `Step.step_text`, `Step.extra_info` and
`Recipe.short_description` are `CharField(max_length=512)`. SQLite ignores the
limit, so imported rows exceed it (3 steps up to 656 chars, 6 blurbs, one
72-char ingredient name vs 64): they display, but the inline editor refuses to
save them, step merge (#18) refuses at 512, and a Postgres move would fail.

**Fix.** Make the three prose fields `TextField`s (optional generous form
limit); choose a deliberate `ingredient_name` limit after checking the data;
drop the redundant `unique=True` on `ingredient_name` (the case-insensitive
constraint covers it). Regenerate `docs/schema.sql`. Land before #19.

### B5 · Stop the HTML sanitiser truncating text after a stray `<`

Issue: #50 · Sources: QA-3

**Problem.** `HTMLParser` treats `<letter…` as a tag start and `close()`
discards the unparsed buffer. `Bake (oven<gas 4) for 20 min. Rest.` renders as
`Bake (oven`; `a<b` renders as `a`. Steps, titles and blurbs all share the
code, so the page and the editor disagree with no hint why.

**Fix.** In `_InlineHtmlSanitizer.result()`, emit any unparsed remainder as
escaped text. Tests: the rows above, plus a property-style test that input
with no allowed tags keeps its visible text.

### B6 · Confirm before deleting a non-empty ingredient group

Issue: #51 · Sources: COR (group delete), UX-8

**Problem.** The group's Delete button has no `hx-confirm`, and rows cascade,
so one click next to Save/Cancel removes the group and every ingredient in it,
with no undo. The view also deletes the recipe's last group, which
`_prune_empty_group` deliberately keeps.

**Fix.** `hx-confirm` naming how many ingredients will go (or refuse a
non-empty delete and point to "Move to"), and keep the last group.

### B7 · Self-host the web fonts

Issue: #52 · Sources: SEC-10, PR-11, PERF-5, DEP-11, LTE-15 · Redesign: **Split**

**Problem.** `base.html` loads Inconsolata and Lobster from
`fonts.googleapis.com` on every page: every visitor's IP goes to Google (ruled
a GDPR breach, LG München I, 3 O 17493/20), it is render-blocking with no
`display=swap`, and it blocks a strict CSP (C1).

**Fix.** Serve `woff2` files from `static/` with
`@font-face { font-display: swap; }` and `<link rel="preload">`.

**Redesign.** The redesign may choose different fonts; self-host whatever it
picks. If the redesign is far off, self-host the current two now.

### B8 · Enforce migrations, `schema.sql` and other cheap invariants in QA/CI

Issue: #53 · Sources: LTE-13, QA-7, TD-2, TD-3, AR-3, PR-9

**Problem.** AGENTS.md requires a migration for every model change and a
regenerated `docs/schema.sql`, but nothing checks either (both happen to be
clean today). `src/recipes/management/` and `commands/` lack `__init__.py`, so
coverage never sees an untested command (`addinitialuser` is 0% and missing
from the report). Undefined template variables render as empty.

**Fix.** A `poe check-migrations` task in `qa`: `makemigrations --check
--dry-run`, migrate a temp SQLite DB, `backup_db --schema-only --schema <tmp>`,
diff against `docs/schema.sql`. Add the two `__init__.py` files,
`branch = true` in `[tool.coverage.run]`, and `--fail-on-template-vars` in
pytest `addopts` (zero violations today).

### B9 · Harden the CI workflow

Issue: #54 · Sources: LTE-13, SEC-12, OSM-4, DEP-4, DEP-6, DEP-7, DEP-10

**Problem.** `ci.yml` has no top-level `permissions:`; actions are on mutable
tags (including third-party `peaceiris/actions-gh-pages` with write access) and
old majors patched with `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`; `uv sync` runs
without `--locked`, so lockfile drift passes; `setup-uv` and pnpm versions
float; there is no `concurrency` or `timeout-minutes`; `apt-get install jq`
runs without `update`; the badge job `pip install`s the unmaintained
`coverage-badge` unpinned with `setuptools<81`.

**Fix.** `permissions: contents: read` at workflow level (`write` only on
`badge`); SHA-pin actions at current majors and drop the Node 24 override;
`uv sync --locked --all-groups` and pin `setup-uv`'s `version`;
`"packageManager": "pnpm@10.28.0"` in `package.json`; a `concurrency` group
with cancel-in-progress and `timeout-minutes`; drop the `jq` step (preinstalled,
see C9); replace `coverage-badge` with a pinned maintained tool via `uvx` or a
shields.io endpoint JSON.

### B10 · Automate dependency updates and vulnerability scanning

Issue: #55 · Sources: LTE-13, SEC-06, PR-9, OSM-3, TD-10, DEP-3

**Problem.** No Dependabot or Renovate, and no audit step, which is how the
A7 advisories accumulated unnoticed. Four ecosystems drift independently
(uv, pnpm, GitHub Actions, pre-commit revs, which are already behind).

**Fix.** `.github/dependabot.yml` for `uv`, `npm` and `github-actions`,
weekly, grouped minor/patch. A CI audit step (`uvx pip-audit` over `uv export`,
`pnpm audit --audit-level=high`). `pre-commit autoupdate` monthly (or Renovate
to cover it too). Turn on Dependabot alerts and private vulnerability
reporting.

### B11 · Delete dead scripts and legacy code

Issue: #56 · Sources: LTE-12, SEC-11, OSM-9, TD-7, LT-9, ARCH-11

**Problem.** Dead code reads as supported, and the scripts that write to the
database are a hazard once the repo is on a server:

- `scripts/sql_to_edit_recipes_hack/` interpolates arguments into raw SQL,
  hard-codes `/Users/fritz/...` and bypasses cascades and sequence compaction
  (superseded by `delete_recipe` and the inline editor).
- `scripts/backfill_step_titles.py` says "delete once it has been run" (#20
  shipped).
- `fix_duplicate_sequences` existed for migration 0007.
- `natural_key()` on every model and `RecipeManager.get_by_natural_key` served
  the removed YAML import; several keys are not even unique.
- `.ruff.toml` excludes `src/jobs/migrations`, which does not exist.

**Fix.** Delete all of the above with their tests. (Squashing migrations is D7.)

### B12 · Make the documented `manage.py` commands work on a fresh checkout

Issue: #57 · Sources: DX-2, AR-2, OSM-8

**Problem.** `manage.py` defaults to `nutrisho.settings.prod`; only poe tasks
get dev settings. AGENTS.md's mandated schema commands
(`uv run python manage.py migrate`, `backup_db --schema-only`) die on a fresh
checkout with `ImproperlyConfigured: Set the SECRET_KEY…`; with a `.env`,
`manage.py runserver` serves an unstyled app with no hint why. The README and
developer guide also use bare `python manage.py`, which AGENTS.md forbids.

**Fix.** Keep `manage.py` on prod (safer for deploys) and add `poe manage`
(passthrough with dev env) and `poe schema` tasks. Point AGENTS.md, the README
and the developer guide at them; no bare `python` anywhere.

### B13 · Search, filter and paginate the recipe list → #32

Issue: **#32** (existing) · Sources: LTE-08, UX-5, LT-8 · Redesign: **Design-led**

Scope added to #32 rather than a new issue:

- Search must match text with inline HTML stripped (since #17, a query for
  `u` matches every underlined title); the per-owner uniqueness check has the
  same problem (`Foo` vs `<u>Foo</u>`).
- Cuisine and tag filters (depend on C4), pagination, the HTMX active-search
  pattern the ingredient tool already uses.
- Ingredient search answers "what can I cook with the aubergine in the
  fridge".
- Prev/next on the detail page walks by id ascending while the list sorts
  newest first; carry the list query into the detail page.

### B14 · Responsive layout with a read/cook mode

Issue: #58 · Sources: UX-4, A11Y-10 · Redesign: **Design-led**

**Problem.** `.recipe-contents` is a fixed `1040px × 18cm` card with no media
queries, so phones pan sideways; the fixed navbar covers the title at 125%
zoom; all type is in px. Everything is click-to-edit with no read mode, so a
tap to scroll on a touch screen opens an editor. The kitchen tablet is the main
place a recipe is read, and the VPS makes it reachable.

**Fix (for the design).** Single column below ~768px (ingredients above
steps), `max-width` not `width`, no fixed height on screen, content offset so
the navbar never overlaps, `rem` type. A read/cook mode as default with an
explicit Edit toggle; optionally Wake Lock and ticking off ingredients/steps.
Keep print working.

### B15 · Add log-out and a proper login page

Issue: #59 · Sources: UX-7 · Redesign: **Design-led**

**Problem.** There is no log-out control anywhere (`LogoutView` needs a POST
and no template sends one), so the user cannot sign out of a borrowed device.
The login page is an unstyled `form.as_p` without the app chrome.

**Fix.** A POST log-out button in the list header and recipe navbar; the login
page extends the base template. Placement and look belong to the redesign; a
plain log-out form can land earlier if the redesign slips. (Root-page redirect
is in C13.)

### B16 · Make every control keyboard-reachable and named

Issue: #60 · Sources: A11Y-1, A11Y-2, A11Y-3, A11Y-5, A11Y-6 · Redesign: **Split**

**Problem.** Inline editing starts from clicks on non-focusable `<span>`,
`<div>` and `<h4>` elements, so keyboard and switch users cannot edit at all.
Recipe matches in the ingredient manager are `<a hx-get>` without `href`, so
they cannot be focused. Icon-only links and buttons (navbar, edit/scale/delete)
have no accessible name, and panel toggles expose no state. Row checkboxes,
select-all, step title/text and "New group name" have no labels. ↑/↓ buttons
are 15×15px (below 24×24) and read as "upwards arrow".

**Fix.** Edit triggers as `<button type="button">` (Escape cancels); matches as
buttons; `aria-label`/`title` on icon controls with `aria-hidden` SVGs;
`aria-expanded`/`aria-controls` on toggles; labels on every input ("Select
step 2", "Select onion"); 24×24px targets labelled "Move step 2 up".

**Redesign.** Bake these in as acceptance criteria. The matches-as-buttons and
`aria-label` fixes are template one-liners worth landing now.

### B17 · Manage focus and announce changes after HTMX swaps

Issue: #61 · Sources: A11Y-4, A11Y-7 · Redesign: **Split**

**Problem.** After a move, Save, Cancel or Delete, the swapped region drops
focus to `<body>`; opening an edit form or the metadata panel does not move
focus into it (the panel is injected earlier in the DOM than its trigger);
boosted navigation leaves focus on `<body>` with no announcement. No live
regions exist, so selection counts, "Saved", 422 `.form-error` messages and
deletions are silent to screen readers; two hand-rendered inputs miss
`aria-invalid`/`aria-describedby`.

**Fix.** `autofocus` on the first field of each form; stable ids on move
buttons so htmx restores focus; focus the replacing display element after
Save/Cancel; focus `<h1 tabindex="-1">` after boosted swaps; `role="status"` on
counts and "Saved", `role="alert"` on `.form-error`; error attributes on the
two inputs. Pairs with A4's error banner.

---

## C — P3

### C1 · Move inline JavaScript to static files and add a CSP

Issue: #62 · Sources: SEC-09, TD-6, LTE-15, LTE-14 · Redesign: **Split**

**Problem.** `base.html` carries ~70 lines of inline JS (autosize, steps panel,
reassign panel, `panelToggle`) loaded on every page including login; it cannot
be linted, cached or tested. 18 inline `onclick`/`onchange` handlers and Google
Fonts (B7) block a Content-Security-Policy, which is cheap defence in depth for
an app that renders user HTML on purpose.

**Fix.** Move the script to `static/js/` (loaded by the pages that need it),
replace inline handlers with delegated listeners, add `"allowEval": false` to
`htmx-config`, then enable Django 6's built-in CSP middleware in report-only
mode and enforce once clean. The redesign will rewrite templates; do this as
part of it, or first if the redesign is far off.

### C2 · Add browser smoke tests for the HTMX flows

Issue: #63 · Sources: LTE-14, QA-6, TD-6 · Redesign: **Split**

**Problem.** The suite uses the Django test client, so `hx-include`, OOB swaps,
`HX-Retarget`, the DOM-position insert calculation, split-at-cursor offsets
(code points, CRLF) and bulk-selection panel state are never executed. A
manual Playwright run found no breakage today, but nothing keeps it that way.

**Fix.** `pytest-playwright` with `live_server`, marked `e2e`, run in CI on
Chromium (build `output.css` first), not in pre-commit: login; add/edit/move/
split/merge/bulk-delete steps; add a group and ingredients; scale; an
ingredient-tool merge; A4's error banner. Write the journeys against the
redesigned UI if it is imminent; otherwise start with two or three now.

### C3 · Fix N+1 queries when HTMX endpoints re-render

Issue: #64 · Sources: PERF-2

**Problem.** The recipe page is a constant 10 queries, but endpoints that
re-render `_groups_list.html`/`_iir_list.html` pass an un-prefetched recipe.
At 6 groups × 20 rows: `group_move` 138 queries, `ingredient_reassign` 164,
`ingredient_manage_preview` 251.

**Fix.** A `recipe_with_contents(recipe_id, owner)` helper holding the existing
`Prefetch` plus `select_related("ingredient", "substitute")`, used by every
render that walks groups or rows; prefetch on the group for `_iir_list.html`.
`django_assert_num_queries` tests at two sizes asserting the count does not
grow.

### C4 · Show or drop the schema fields the UI hides

Issue: #65 · Sources: LTE-07, UX-6, LT-6, COR (substitutes) · Redesign: **Split**

**Problem.** Several fields are migrated, copied and backed up but nobody can
see or set them: `Tag` (no UI at all), `Cuisine` (editable, never shown),
`source_instance` (only visible in the metadata panel, not clickable), `Source`
(never written), `IngredientInRecipe.substitute` (repointed by the clean-up
tool, never shown or editable), `Step.duration`/`extra_info` (never written;
split drops them), `Ingredient.family`/`dietary_constraint` (never displayed or
rolled up). `Cuisine.cuisine`'s verbose name is still a placeholder.

**Fix.** Decide field by field. Suggested: show tags, cuisine, source (as a
link) and substitute ("or X", plus a field in the inline form, resolved like
`ingredient_name`); make tags editable; drop `Source`, `duration` and
`extra_info` in a migration unless #19 needs them.

**Redesign.** The keep/drop decision and the substitute form field are
backend work for now; where these appear on the page is for the design.

### C5 · Resolve aliases and plurals on ingredient input

Issue: #66 · Sources: COR (plurals), OSM-10, plan 008, #14

**Problem.** With `onion` stored, typing `2 onions` creates an `onions` row,
recreating the duplicates "Merge plural" exists to remove. Plan 008 (aliases,
"Approved — ready to implement") still tracks #14, which is closed.

**Fix.** Implement plan 008 inside A1's `resolve_ingredient`: after the
case-insensitive miss, match existing rows' plural forms (rule or override),
then aliases. Re-point plan 008 at this issue.

### C6 · Normalise units

Issue: #67 · Sources: LTE-11, LT-7

**Problem.** `unit` is free text: `Tbsp` (268), `tbsp` (226), `tbs`, `tbso`;
`clove`/`cloves`; `l`/`L`; non-units such as `small`, `large`, `to taste`. The
page already renders "2 small onion" (any non-empty unit counts as a measure)
and scaling multiplies "to taste". Shopping lists, conversion, nutrition and
#19's templates all need canonical units.

**Fix.** A canonical unit vocabulary with aliases (same shape as plan 008) and
a dimension (mass/volume/count), resolved on input; a reviewed management
command to migrate values; size words into `preparation`; pluralise units at
display time.

### C7 · Tidy the poe test and QA tasks

Issue: #68 · Sources: DX-3, DX-4, DX-8, AR-4, AR-5, DEP-9

**Problem.** `poe test <path>` always fails the 95% coverage gate on a subset,
so the mandated TDD loop can't use it; `-vv -s` prints ~870 lines per passing
run (costly for agents, buries failures). `qa` starts with a non-frozen
`pnpm install` and a Tailwind build no test reads, so Python-only changes need
Node and network. `poe coverage` uses macOS `open`. The commitizen hook
hard-codes `.venv/bin/cz`. Nothing says to run `pre-commit install`, and
nothing checks PR titles although they become the squash subject.

**Fix.** Split `test` (plain pytest, args pass through, no `-vv -s`, optional
`--tb=short`) from `test-cov` (used by `qa`); `pnpm install --frozen-lockfile`;
a Python-only `qa` gate, with the CSS build in CI and `dev`;
`python -m webbrowser` for coverage; `entry: uv run cz check`; add
`uv run pre-commit install` to setup; a CI job linting PR titles.

### C8 · Fix documentation drift

Issue: #69 · Sources: LTE-16, DX-4, DX-6, OSM-8, OSM-10, TD-9, AR-7, AR-12, LT-9

**Problem.** The developer guide still prescribes `feature/<name>` branches
(retired in AGENTS.md); README "What it does" lists only browsing. AGENTS.md
mandates `click`, `pydantic` and `pytest-data`, none of which the code uses
(`faker`/`polyfactory` are unused dev deps). Plans 005 and 006 have been
"Draft" since May (005 asks about FloatField, already a DecimalField).
`initial-context.md` is 310 lines of feature changelog and says "no
production settings". `pyproject.toml` has placeholder authors and "Quick and
dirty django prototype". The assessment backlog sat in `docs/plans/`, which
agents read at every start.

**Fix.** Align the branch section with AGENTS.md (or link it); update README;
replace AGENTS.md's library rules with actual practice and drop unused dev
deps; archive or rewrite 005/006; move feature notes to `docs/features/` and
trim `initial-context.md` to ~100 lines of architecture; fix package metadata.
Archive this plan once its issues are filed (the raw reports already live in
`docs/reviews/`).

### C9 · Tidy the committed Claude Code configuration

Issue: #70 · Sources: DX-5, TD-8, AR-1, AR-8, AR-9, AR-10, AR-11

**Problem.** `.claude/settings.json` (applies to every contributor) switches
assistants into caveman mode, writes to `~/.claude` and replaces the status
line. The branch-prompt SessionStart hook uses matcher `*`, so it fires after
every compaction and stalls headless runs. `test-hooks` runs in `qa` but tests
a copy of the regexes, and is the only reason CI needs `jq`. Hooks use
relative paths; there is no permission allowlist for the mandated commands;
the TDD skill is not in a discoverable `<name>/SKILL.md` layout; caveman mode
does not exempt docs.

**Fix.** Move caveman hooks and status line to user-level or
`settings.local.json`; take `test-hooks` out of `qa` (or make it source the
real patterns); branch hook on `startup` only, reworded for non-interactive
runs (also in AGENTS.md); `$CLAUDE_PROJECT_DIR` paths; an allowlist for
`uv run poe *`, `uv run pytest *`, read-only git; move the skill to
`.claude/skills/tdd/SKILL.md`; exempt `*.md` from caveman mode.

### C10 · Add a demo-data seed command

Issue: #71 · Sources: DX-9, AR-6

**Problem.** A fresh database is empty, so trying the ingredient clean-up tool
or reviewing a UI change means hand-building recipes with duplicates, plurals,
groups, substitutes and step titles every time.

**Fix.** A `seed_demo` management command (`uv run poe seed`) that creates a
dev user's worth of sample recipes covering those cases, refusing to run under
prod settings.

### C11 · Cut versioned releases with a changelog

Issue: #72 · Sources: OSM-5

**Problem.** No tags or releases; `pyproject.toml` has been `0.2.0`
throughout and `package.json` says `1.0.0`. Once deployed, "what is running"
and "roll back" have no answer but a SHA.

**Fix.** Configure `[tool.commitizen]` (version in `pyproject.toml`,
`update_changelog_on_bump = true`), cut `v0.3.0` with `cz bump`, deploy tags;
mark the `package.json` version irrelevant.

### C12 · Upgrade off Django 6.0 before its support ends

Issue: #73 · Sources: OSM-3, DEP-8

**Problem.** `Django ~=6.0.0` blocks 6.1 (6.1.2 current). 6.0 gets security
fixes only until April 2027; nothing tracks that deadline.

**Fix.** Widen to `~=6.1` now (run with `-W error::DeprecationWarning` first),
plan the 6.2 LTS move for spring 2027, then stay on LTS. Deadline: before
April 2027.

### C13 · Fix page structure: landmarks, headings, language, contrast

Issue: #74 · Sources: A11Y-8, A11Y-9, A11Y-11, A11Y-12, ARCH-11, LTE-15 · Redesign: **Split**

**Problem.** `<html lang="">` on every page; the root view (`/`, where login
lands) is a bare inline `<h1><a>` fragment with no doctype or title, breaking
the "`src/nutrisho/` is configuration only" rule. No `<main>`, navbar is a
`<div>`, the recipe title is not an `<h1>` and there are no Ingredients/Method
headings. Edit fields have a 1.8:1 dotted silver border. Recipe list actions
are dozens of identical "View"/"Delete" links that precede the recipe name.

**Fix.** Now: `lang="en"`, and redirect `/` to `recipes:home`. With the
redesign: `<main>`, `<nav aria-label>`, a heading outline (`<h1>` title,
`<h2>` Ingredients/Method, `<h3>` groups), input borders ≥ `#767676`, recipe
name in each action's accessible name and first in DOM order.

---

## One day — Backlog

### D1 · Soft-delete recipes with undo

Issue: #75 · Sources: UX-8 · Redesign: **Split**

Recipe delete is one click plus `confirm()` sitting between frequently used
buttons; ingredient-tool merges and deletes rewrite every affected recipe with
no way back. Add `deleted_at` to recipes (hidden from the list, an "Undo"
toast, a trash view), move Delete away from common buttons, and record
merges/deletes so they can be reversed. Soft delete is a model change; the
toast, trash view and button placement are for the design. A11 is the safety
net until then.

### D2 · Pick one styling system

Issue: #76 · Sources: LTE-15, AR-5 · Redesign: **Design-led**

Tailwind v4 provides ~26 utility classes (mostly the ingredient tool) while
370 lines of hand-written `style.css` cover the rest, and Tailwind is the only
reason the project needs Node and pnpm in CI, pre-commit and setup. The
redesign should choose: move everything to Tailwind, or convert the utilities
to plain CSS and drop the Node toolchain (cheaper for a server-rendered HTMX
app).

### D3 · Move domain logic into services and slim the view layer

Issue: #77 · Sources: ARCH-9, LT-4, TD-5

Only the clean-up tool follows the documented services boundary. Duplicate,
scale, reassign, group pruning, ingredient resolution and step merge/split live
in views (`recipe_ingredients.py` is 567 lines), so they cannot be reused by a
command, importer or API. Every endpoint touches four lists (view,
`views/__init__.py` imports and `__all__`, `urls.py` imports, `path()`), and
up/down moves are six near-identical views. No big-bang refactor: move logic
into `services/` as it is touched (A1 and A2 start it), import view modules
directly in `urls.py` and drop the barrel, and collapse each up/down pair into
one view taking `direction` from the URL.

### D4 · Import recipes from JSON-LD or pasted text

Issue: #78 · Sources: LT-5

Since the YAML import was removed (#27), recipes can only be typed in field by
field. One importer behind a service function, fed by schema.org `Recipe`
JSON-LD or pasted text (one ingredient per line, one step per paragraph), is
the natural place for alias resolution (C5), unit resolution (C6) and
`utils/step_title.py`.

### D5 · Rename reverse accessors to plurals

Issue: #79 · Sources: ARCH-11

`recipe.step`, `recipe.tag`, `recipe.ingredients_group`,
`ingredient_group.ingredient` (which yields `IngredientInRecipe` rows) and the
`Tag` M2M called `recipe` read as single objects. Rename the `related_name`s to
`steps`, `tags`, `ingredient_groups`, `items`: no SQL change, only Python and
templates. Best done with or after D3.

### D6 · Replace the ingredient datalist with an autocomplete endpoint

Issue: #80 · Sources: PERF-4

Every inline ingredient edit ships the whole ingredient table as a
`<datalist>` (114 KB per click at 2,000 ingredients), and the clean-up tool's
column 2 renders every ingredient (597 KB). Proxy compression (A12) covers it
for now; when the table grows, add an `hx-get` autocomplete returning the top
20 matches, and paginate column 2.

### D7 · Squash migrations 0001–0016

Issue: #81 · Sources: TD-7

A fresh install runs dead data migrations (e.g. ~100 lines in
`0008_sanitize_yaml_filenames` for a column `0016` drops). With a single
deployment, `squashmigrations` and remove the originals once the VPS has
applied the squash. Do after A12 so the production database exists.
