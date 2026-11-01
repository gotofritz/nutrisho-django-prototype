# Assessment reports (raw, 2026-10-30)

The unedited reports from the 2026-10-30 assessment, kept for traceability.
The de-duplicated, prioritised plan is [`docs/plans/01-issues.md`](../plans/01-issues.md),
and every item there lists the report IDs it was merged from. Unprefixed
sections (day-to-day correctness) are cited as `COR` in the plan.

## Long-term evolution assessment (external architect, 2026-10-30)

This is an independent review of `main` at `4b84cd3`. Every "Verified" note was
reproduced on that commit with a throwaway test. Issues are ordered by priority
within each band. IDs carry an `LTE-` prefix so they cannot clash with numbering
used elsewhere in this file. Where an issue overlaps an open GitHub issue, that
issue is named and the scope here is merged into it.

### P1: broken or losing data today

#### LTE-01 Resolve ingredient names case-insensitively, in one place

**Problem.** The database enforces
`UniqueConstraint(Lower("ingredient_name"))` (migration 0013), but the
recipe-page write paths look names up with a case-sensitive
`get_or_create(ingredient_name=name)`:

- `views/recipe_ingredients.py:165`
- `forms/ingredient_forms.py:36`, `:41` and `:51`

A name that differs from an existing one only by case misses the lookup, then
tries to insert and hits the constraint. Verified: adding `Onion` to a recipe
while `onion` exists returns **HTTP 500**.

**Proposal.** Add one service, `resolve_ingredient(name) -> Ingredient`. It
strips the name, looks it up with `ingredient_name__iexact`, and creates a row
only when nothing matches. Route the form and the create and save views through
it. Plan 008 step 3 already prescribes exactly this function for aliases.
Shipping the case-insensitive part now fixes the 500, and alias resolution then
becomes one more lookup inside the same function.

**Done when** the reproduction above has a regression test and every
`Ingredient.objects.get_or_create` in `src/` goes through the service.

#### LTE-02 Make "Duplicate recipe" copy every field, including step titles

**Problem.** `recipe_duplicate` (`views/recipe_crud.py`) copies `Step` rows
field by field, and the list was not updated when `step_title` arrived
(migration 0015). Verified: duplicating a recipe whose step is titled `Ragu`
gives a copy with `step_title == ''`. Any new field on `Step`, `IngredientGroup`
or `IngredientInRecipe` will be dropped the same way, without warning. The risk
grows with #19, which adds new fields to `Step` for reusable steps and template
variables.

**Proposal.** Copy rows generically from `_meta.concrete_fields`, leaving out
the pk and the parent FK. Add a test that walks those same fields, so the next
new column makes a test fail instead of disappearing.

#### LTE-03 Align field lengths with the data

**Problem.** SQLite does not enforce `VARCHAR(n)`. The recipes imported before
#29 therefore hold values longer than their fields allow. The former
`recipes_yaml/` corpus contained:

- 3 steps longer than the 512 characters `Step.step_text` allows. The longest,
  in *Borscht*, has 656.
- 6 blurbs longer than the 512 characters `short_description` allows.
- 1 ingredient name of 72 characters, where the limit is 64.

Those rows display fine, but the inline editor's `ModelForm` refuses to save
them until they are shortened. Merging steps (#33) hits the same 512 limit and
refuses the merge. Migrating to PostgreSQL would fail on these rows.

To find the affected rows, run:

```sql
SELECT id, length(step_text) FROM recipes_step WHERE length(step_text) > 512;
SELECT id, length(short_description) FROM recipes_recipe WHERE length(short_description) > 512;
```

**Proposal.**

- Make `step_text` and `short_description` `TextField`s. They are prose and
  have no natural limit. This also removes the merge refusal.
- Choose a deliberate limit for `ingredient_name`.
- While touching `Ingredient`, drop `unique=True` from `ingredient_name`. The
  case-insensitive constraint already covers it.
- Land this before #19, which makes the step model richer.

#### LTE-04 Bootstrap a usable account on a fresh checkout

**Problem.** The developer guide says a fresh checkout starts with
`poe migrate` and then `addinitialuser`. Two things go wrong from there:

- `addinitialuser` creates `gotofritz` with `User.objects.create(...)`, so the
  account has no usable password and nobody can log in as it.
- `poe createsuperuser` creates a *different* user, `fritz`, with the password
  `fritz` and a personal email address, all hard-coded in `.poe.toml`.

The account that can log in and the account the guide sets up are not the same
one, and credentials sit in the repository.

**Proposal.** Replace both with one `poe bootstrap` task. It creates a single
owner via `create_superuser`, takes the username, email and password from the
environment (documented in `.env.example`), and does nothing if the user
already exists.

### P2: architecture that will hurt as the app grows

#### LTE-05 Scale recipes at display time instead of rewriting stored quantities

**Problem.** `recipe_scale` overwrites every `IngredientInRecipe.quantity`,
rounded to 0.01, and `Recipe.servings`, rounded to a whole number. Since #29 the
database is the only copy of a recipe, so this destroys data:

- **It can't be undone.** Scaling by ⅓ and then by 3 does not give back the
  original quantities.
- **Servings and quantities drift apart.** Scaling `servings=1` by 1.5 stores 2
  servings while the quantities grow by exactly ×1.5.
- **It leaks into other code.** `display_ingredient_name` has to guard against
  "2 onion" because scaled quantities are persisted.

**Proposal.** Treat scaling as presentation. The recipe page accepts a target
serving count (`?servings=6`), kept in the URL so the scaled view can be
bookmarked and printed. Displayed quantities are computed from the stored ones.
If keeping a scaled version is wanted, offer "Save as scaled copy", which reuses
duplicate (LTE-02).

#### LTE-06 Make backups automatic, kept outside the repo, and proven to restore

**Problem.** Since #29, `db.sqlite3` is the only copy of the data, and
`backup_db` is the only protection. It has three gaps:

- **It is manual.** Nothing runs it, so the newest backup is as old as the
  last time someone remembered.
- **It writes into the repository.** Dumps go to `docs/dump-*.sql`, which is
  git-ignored. A dump contains every row, including `auth_user` password
  hashes and `django_session` data. It sits next to the code, so it travels
  with any copy or sync of the working tree.
- **Restoring is never tested.** The tests check what the dump contains, but
  never load one back. The documented restore,
  `sqlite3 db.sqlite3 < dump.sql`, has no test showing it works.

**Proposal.**

- Default the dump directory to a setting (`BACKUP_DIR`, outside the repo),
  keep the last *N* dumps, and document a cron or launchd line, or run it from
  `poe dev` at start-up.
- Add a test that dumps a populated database, restores the dump into a fresh
  one, and compares row counts per table.
- Consider SQLite's backup API (`connection.backup()`) or `VACUUM INTO`. Either
  gives a consistent binary copy that restores faster than replaying SQL.

#### LTE-07 Surface the schema fields the UI hides, or remove them

**Problem.** With YAML gone, several modelled fields cannot be written by
anything except Django admin, and nothing displays them:

| Field or model | State on `main` |
|---|---|
| `Tag` | Legacy rows exist. Not shown on the recipe page, not editable, not filterable. Copied by duplicate. |
| `Cuisine` | Editable in the metadata form, but not shown on the recipe page. |
| `Source` (model) | Never written by any code path. |
| `IngredientInRecipe.substitute` | Never written. The clean-up tool only repoints it. |
| `Step.duration`, `Step.extra_info` | Never written. Split drops them. |

Every unused column still costs a migration, and code that has to handle it,
each time the model changes.

**Proposal.** Decide field by field. Suggested starting point:

- **Show:** tags, cuisine, `source_instance`, and `substitute` (rendered as
  "or X").
- **Make editable:** tags.
- **Drop in a migration:** `Source`, `duration` and `extra_info`, unless #19
  or another concrete plan needs them.

#### LTE-08 Search, filter and paginate the recipe list (merge into #32)

**Problem.** `/recipes/` shows every recipe in one unpaginated list, with no
search and no filters. #32 already asks for a site-wide search box with OR
semantics across title and ingredients. This issue adds the parts #32 does not
cover:

- **Filters.** Add cuisine and tag chips (they depend on LTE-07) and
  pagination, using the HTMX active-search pattern the ingredient tool already
  uses.
- **Search on plain text.** Since #31, `recipe_name` and `short_description`
  can contain inline HTML. Search must match against the text with tags
  stripped, or a query for `u` matches every underlined title. That means a
  stored plain-text column or a `Replace`/regex annotation; `icontains` on the
  raw column is not enough. The same applies to the per-owner uniqueness
  check: `Foo` and `<u>Foo</u>` are currently two different names.
- **Prev/next order.** Prev/next on the detail page walks by id, ascending,
  while the list sorts newest first. Carry the list query, including any
  search, into the detail page so prev/next follows what the user was looking
  at.

#### LTE-09 Restrict the global ingredient tool to staff (or commit to single-user)

**Problem.** Recipes are owner-scoped everywhere, which implies more than one
user. `Ingredient`, `Tag` and `Cuisine`, however, are global, and
`/recipes/ingredients/manage/` requires only a login. Any authenticated user can
rename, merge or delete ingredients used by other people's recipes.

**Proposal.** Pick a direction:

- **Multi-user:** gate the `manage/` routes behind `is_staff`, or behind the
  `recipes.change_ingredient` and `recipes.delete_ingredient` permissions, and
  test that an ordinary user gets a 403.
- **Single-user:** state it in `initial-context.md` and stop paying for owner
  scoping.

Staying half-way between the two is the risky option.

#### LTE-10 Make login enforcement secure by default with `LoginRequiredMiddleware`

**Problem.** Authentication is opt-in per route. Each of the roughly 55 entries
in `recipes/urls.py` is wrapped by hand in `_lr()`. #33 added three more routes
that needed the same wrapper. A future route that misses it reaches its view
anonymously, and the view's `owner=request.user` query then fails with a 500
instead of redirecting.

**Proposal.** Use Django's `LoginRequiredMiddleware` (5.1+). Subclass it so
`handle_no_permission` keeps the `HX-Redirect` behaviour from
`views/_auth.py`, and mark the auth views `@login_not_required`. Then delete
`_lr()`. Add one test that iterates every URL pattern and asserts that an
anonymous request never gets a 200 or a 500.

#### LTE-11 Normalise units before building anything on quantities

**Problem.** `unit` is free text. The legacy data, as seen in the former
`recipes_yaml/` corpus, mixes several spellings of the same unit and words that
are not units:

| Kind of problem | Examples (counts) |
|---|---|
| Same unit, different spelling | `Tbsp` (268), `tbsp` (226), `tbs` (7), `tbso` (2) |
| Singular and plural stored separately | `clove`/`cloves`, `cup`/`cups`, `sprig`/`sprigs` |
| Case variants | `l`/`L` |
| Words that are not units | `small`, `medium`, `large`, `to taste` |

This already causes wrong output today:

- The pluralisation gate treats any non-empty unit as a measure, so the page
  renders "2 small onion".
- Scaling multiplies quantities that sit next to "to taste".

It also blocks later work. Shopping lists, unit conversion, the nutrition
features the name *Nutrisho* suggests, and #19's templated steps all need
canonical units.

**Proposal.**

- Introduce a canonical unit vocabulary with aliases, the same shape as
  plan 008's ingredient aliases, and resolve units on input.
- Migrate existing values with a reviewed management command, the way
  ingredients were cleaned up.
- Move size words such as `small` or `large` into `preparation`.
- Pluralise units too, so "1 clove" and "2 cloves" come from one stored value.

### P3: tooling, quality and hygiene

#### LTE-12 Prune runtime dependencies and leftover scripts

**Problem.**

- `google-genai` is listed in `[project].dependencies`, but nothing imports it.
- `django-debug-toolbar` is loaded only by `settings/dev.py`, yet it ships as
  a runtime dependency.
- `scripts/sql_to_edit_recipes_hack/` hard-codes `/Users/fritz/...` and
  deletes rows with hand-written SQL. `delete_recipe` and the inline editor
  have both replaced it.

**Proposal.** Remove `google-genai`, move `django-debug-toolbar` to the `dev`
group, and delete the SQL hacks. Git keeps the history if they are ever needed.

#### LTE-13 Harden CI: locked installs, schema and migration drift, dependency updates

**Problem.**

- **Lockfile drift passes CI.** CI runs `uv sync --all-groups` without
  `--locked`, so a `pyproject.toml` change with a stale `uv.lock` passes.
- **uv is unpinned.** `setup-uv` installs whatever version is current. A local
  `uv sync` with a different uv version rewrote the lock header during this
  review.
- **`docs/schema.sql` relies on memory.** AGENTS.md requires regenerating it
  in every PR that touches migrations, but nothing checks that it was done.
  Likewise, nothing checks that model changes come with a migration.
- **No dependency updates.** There is no Dependabot or Renovate for Python,
  pnpm, GitHub Actions or the pre-commit hook revisions. The project is pinned
  to Python 3.14 and Django 6.0, which both move fast.

**Proposal.**

- Run `uv sync --locked --all-groups` and pin `version:` in `setup-uv`.
- Add a CI step that runs `migrate`, `makemigrations --check --dry-run`,
  `backup_db --schema-only`, and finally `git diff --exit-code docs/schema.sql`.
- Add `.github/dependabot.yml` for `uv`, `npm` and `github-actions`, plus a
  monthly `pre-commit autoupdate`.

#### LTE-14 Add a small browser test suite for the HTMX flows

**Problem.** All tests use Django's test client and assert on the HTML it
returns. But the UI's correctness depends on things only a browser runs:

- `hx-include` selectors, out-of-band swaps and `HX-Retarget`.
- The growing inline JavaScript in `base.html`. #33 added
  `_syncStepsPanel` alongside the existing reassign-panel logic.
- #33's split-at-cursor feature, which depends on the textarea's cursor
  offset and on CRLF normalisation.

`initial-context.md` documents pitfalls of exactly this kind, and a server-side
test cannot catch any of them.

**Proposal.** Add `pytest-playwright` with `live_server` and a handful of smoke
flows:

- Add, edit and reorder a step.
- Split a step at the cursor, then merge two steps.
- Add an ingredient to a group.
- Merge two ingredients in the clean-up tool.

Mark them `e2e`, run them in CI, and keep them out of the pre-commit hook.

#### LTE-15 Pick one styling approach and move inline JS into a static file

**Problem.** The frontend mixes two styling systems. Tailwind v4 provides about
26 utility classes, mostly in the ingredient tool. 370 lines of hand-written
`style.css` cover everything else. Tailwind is the only reason the project
needs Node and pnpm, in CI, in pre-commit and in local setup.

The page shell has its own loose ends:

- `base.html` carries a growing block of inline JavaScript (see LTE-14) that
  can't be linted, cached or tested.
- Fonts load from the Google Fonts CDN.
- `<html lang="">` is empty.

**Proposal.**

- Choose one styling system. Either move the remaining styles to Tailwind, or
  convert the 26 utilities to plain CSS and drop the Node toolchain. The second
  is cheaper and fits a server-rendered HTMX app.
- Move the inline scripts to `static/js/app.js`.
- Self-host the two fonts.
- Set `lang="en"`.

#### LTE-16 Fix doc drift and keep `initial-context.md` focused on architecture

**Problem.**

- `docs/developer-guide.md` still prescribes `feature/<name>` branches, which
  `AGENTS.md` retired.
- The developer guide and the README use bare `python manage.py`, which
  `AGENTS.md` forbids.
- Plans 005 and 006 have been "Draft" since May. Plan 005 still asks to review
  "FloatField vs DecimalField", though quantity is already a `DecimalField`.
- `initial-context.md` is the document every contributor and agent must read
  first. It is now 310 lines and reads like a feature changelog: Miller-column
  UI behaviour, panel-closing rules, `HX-Retarget` details. The architecture is
  hard to find in it, and the whole file has to be read every time.

**Proposal.**

- Fix the branch and command examples.
- Re-scope or archive plans 005 and 006.
- Move the feature-level notes into `docs/features/<feature>.md`.
- Trim `initial-context.md` to the stack, boundaries, core patterns and
  constraints, at about 100 lines.


---

## Security assessment: risk and attack surface (2026-10-30)

Independent review of `main` at `4b84cd3`, written with the planned move to a
public VPS in mind. Evidence was gathered with
`manage.py check --deploy` against `nutrisho.settings.prod`, `pip-audit` over
`uv export --no-dev`, a read of every view's ownership checks, and a payload
run against the inline HTML sanitiser.

**What is already sound** (so nobody spends time on it): every recipe-scoped
view looks the recipe up with `owner=request.user` and children with
`recipe=recipe`, so there is no IDOR on recipes, steps, groups or ingredient
rows. Model forms whitelist their fields, so `owner` can't be mass-assigned.
`_InlineHtmlSanitizer` held up against script, attribute, comment, CDATA,
unclosed-tag and nesting payloads. The `next=` built by `htmx_login_required`
is checked by `LoginView`, so it is not an open redirect. CSRF is enforced on
every POST, including HTMX through `hx-headers`. There is no self-signup.

Severity is for the VPS scenario: internet-facing, one or a few users.

### SEC-01 · High · `poe createsuperuser` sets the password `fritz`

`.poe.toml` runs `createsuperuser --noinput --username fritz` with
`DJANGO_SUPERUSER_PASSWORD = "fritz"`. If anyone runs it on the VPS, the
result is a superuser with a guessable password behind a public `/admin/`
that has no rate limit (see SEC-04). That is a full takeover.

- Drop the hard-coded password. Either let `createsuperuser` prompt for it,
  or read `DJANGO_SUPERUSER_PASSWORD` from the caller's environment with no
  default.
- Rotate the password of any account created this way before it reaches a
  server.

### SEC-02 · High · Known `SECRET_KEY` values, and prod does not refuse them

- A real key, `django-insecure-p8!)m+w+66=…`, sits in git history, from the
  `settings.py` that predates `django-environ`. Anyone who can read the repo
  has it.
- `dev.py` quietly falls back to `dev-insecure-key-not-for-production` when
  `.env` has none, and `.env.example` ships `change-me-to-a-long-random-string`.

If the VPS ever runs with one of these keys, a forged session cookie or
password-reset token gets anyone in as any user. `prod.py` only requires
*some* key to be set.

- In `prod.py`, raise `ImproperlyConfigured` when the key is shorter than 50
  characters, starts with `django-insecure`, or matches one of the dev, test
  or example placeholders.
- Generate a fresh key on the server. Never reuse a local `.env`.
- Add a CI step: `DJANGO_SETTINGS_MODULE=nutrisho.settings.prod SECRET_KEY=$(openssl rand -hex 40) ALLOWED_HOSTS=example.com uv run python manage.py check --deploy --fail-level WARNING`.
  This also covers SEC-03.

### SEC-03 · High · Production settings have no HTTPS or cookie hardening

`check --deploy` on `prod.py` reports four warnings: W004 (no HSTS), W008 (no
`SECURE_SSL_REDIRECT`), W012 (session cookie not `Secure`) and W016 (CSRF
cookie not `Secure`). As things stand, the session cookie would travel over
plain HTTP on the first non-TLS request.

The VPS will almost certainly terminate TLS at Caddy or nginx, and two more
settings are missing for that:

- Without `SECURE_PROXY_SSL_HEADER`, Django thinks every request is HTTP.
  Turning on `SECURE_SSL_REDIRECT` then causes a redirect loop, and the CSRF
  Origin check rejects HTTPS form posts.
- `CSRF_TRUSTED_ORIGINS` is not set.

Fix: add these to `prod.py`, driven by env vars where they vary per host:

- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `SECURE_SSL_REDIRECT`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_HSTS_SECONDS`: start low, raise it once HTTPS is confirmed stable.

### SEC-04 · Medium · No brute-force protection on the login pages

`/accounts/login/` and `/admin/login/` accept unlimited password guesses, and
failed logins are not logged anywhere (see SEC-07). For a personal app on a
public IP, this is the most likely attack.

- Add `django-axes`, or rate-limit both paths at the reverse proxy
  (`limit_req` in nginx, `rate_limit` in Caddy) and add a fail2ban jail on the
  auth log.
- Since only the owner needs `/admin/`, consider allowing it only from an IP
  allowlist or a VPN such as Tailscale or WireGuard, or at least moving it
  off the default path.

### SEC-05 · Medium · Any logged-in user can rewrite every user's ingredients

The `ingredient_manage_*` views only check that the user is logged in, but
`Ingredient` rows are global. Save, delete-with-replacement, merge and
merge-plural therefore change recipes owned by *other* users. The delete
confirmation even counts recipes across all owners on purpose (see
`docs/initial-context.md`, "Owner scoping"). With one account this is fine.
The day a second account exists, it is broken access control: one user can
write to another user's data.

- Gate the `manage/` routes behind `is_staff`, or a `recipes.change_ingredient`
  permission, and return 403 otherwise.
- Add tests that a non-staff user gets 403 on each mutating route.
- Record the rule in `initial-context.md`.

### SEC-06 · Medium · Unused heavy runtime dependencies widen the supply chain

- `google-genai` is a runtime dependency, but nothing in `src/` or `scripts/`
  imports it. It pulls about 30 transitive packages into production
  (`cryptography`, `google-auth`, `requests`, `httpx`, `pydantic`, and more).
  Today, `pip-audit` flags `certifi 2026.7.22` (PYSEC-2026-4320, fixed in
  2026.10.18), and it arrives only through that tree.
- `django-debug-toolbar` is also a runtime dependency, although only `dev.py`
  uses it.

Fix:

- Remove `google-genai`, and move `django-debug-toolbar` to the `dev` group,
  so that `uv sync --no-dev` on the VPS installs only Django, `django-environ`
  and `django-htmx`.
- Add automated scanning: a `.github/dependabot.yml` for the `uv`,
  `github-actions` and `npm` ecosystems, and a `pip-audit` step in CI.

### SEC-07 · Medium · Nothing in the repo is ready for a VPS deploy

- `STATIC_ROOT` is not set, so `collectstatic` fails.
- There is no WSGI server (gunicorn or uvicorn) and no static-file strategy
  (WhiteNoise, or the proxy serving `STATIC_ROOT`).
- There is no `LOGGING` or `ADMINS`. With `DEBUG=False`, 500 errors, CSRF
  failures and `django.security` events are silently dropped.
- `.poe.toml`'s top-level `[env]` forces `nutrisho.settings.dev` on every
  task. On the server, `poe migrate` and `poe backup` would run with
  `DEBUG=True` and the fallback key from SEC-02, and `poe dev` would put
  `runserver` with the debug toolbar on the network.

The gaps make the unsafe shortcut, `runserver` with dev settings, the easiest
way to get the app online. Fix:

- Set `STATIC_ROOT`.
- Add gunicorn, bound to `127.0.0.1` or a unix socket, behind the TLS proxy.
- Log to stderr or journald, including `django.security` and failed logins.
- Have poe set `DJANGO_SETTINGS_MODULE` only when it is unset, so the server
  can export `nutrisho.settings.prod`.
- Write a short deploy runbook in `docs/`.

### SEC-08 · Medium · Backups contain live sessions and are world-readable

`backup_db` dumps every table, including `auth_user` password hashes and
`django_session`. A leaked dump is therefore a ready-made login: the session
keys work without cracking anything. The dump is written:

- with the default umask, usually `0644` (world-readable on a shared VPS);
- inside the checkout, under `docs/`, one `git add -f` away from a commit;
- with `iterdump()` on a live database, which is not guaranteed to be a
  consistent snapshot while the app writes.

Fix:

- Skip `django_session`.
- Write dumps with mode `0600` to a directory set by an env var, outside the
  repo.
- Take the full copy with `sqlite3.Connection.backup()`.
- On the VPS, keep `db.sqlite3` and `.env` at `0600`, owned by the app user
  and outside any directory the proxy serves.
- Ship backups off the box encrypted, for example with restic or borg.

### SEC-09 · Low · No Content-Security-Policy

The app renders user-supplied HTML on purpose. The sanitiser is sound, but a
CSP is cheap defence in depth if it ever regresses. Django 6.0 has one
built in (`django.middleware.csp.ContentSecurityPolicyMiddleware`,
`SECURE_CSP`, nonces). Three things stand in the way: the inline `<script>`
blocks in `base.html`, 18 inline `onclick`/`onchange` handlers in the
templates, and Google Fonts (SEC-10).

- Move the JS into a static file and replace the inline handlers with the
  delegated listeners `base.html` already uses.
- Add `"allowEval": false` to the existing `htmx-config` meta tag.
- Roll out with `SECURE_CSP_REPORT_ONLY` first, then enforce.

### SEC-10 · Low · Google Fonts leaks every visitor's IP to Google

`base.html` loads Inconsolata and Lobster from `fonts.googleapis.com` on every
page. On a public EU-hosted site, German courts have ruled this a GDPR breach
(LG München I, 3 O 17493/20). It is also a third-party dependency, and it
blocks a strict CSP.

- Self-host the two `woff2` files under `static/` and drop the external link.

### SEC-11 · Low · Leftover raw-SQL scripts bypass the app

`scripts/sql_to_edit_recipes_hack/remove_a_recipe.sh` puts its arguments
straight into SQL (`WHERE recipe_id=$RECIPE_ID`), hard-codes
`/Users/fritz/...`, and skips the ORM's cascades and sequence compaction. The
`delete_recipe` command has replaced it, and the `.sql` files beside it are
hand-edit snippets.

- Delete the directory, so nobody runs it against the server database.

### SEC-12 · Low · CI token and action pinning

- `ci.yml` has no top-level `permissions:`, so the `qa` job, which runs on
  every PR, gets the repository's default `GITHUB_TOKEN` scope.
- Third-party actions are pinned to mutable tags. That includes
  `peaceiris/actions-gh-pages@v4`, which runs with `contents: write`.
- `pip install coverage-badge "setuptools<81"` is unpinned in that same
  write-scoped job.

Fix:

- Set `permissions: contents: read` at workflow level, and keep
  `contents: write` only on `badge`.
- Pin actions to commit SHAs. Dependabot from SEC-06 keeps them current.
- Pin `coverage-badge` to an exact version.

### SEC-13 · Info · VPS baseline (outside the repo, but part of the exposure)

- Allow SSH by key only, with no root login.
- Firewall everything except 22, 80 and 443.
- Run `unattended-upgrades`.
- Run the app under its own unprivileged user, with a systemd unit hardened by
  `ProtectSystem=strict`, `NoNewPrivileges=yes` and `ReadWritePaths` limited
  to the database and backup directories.
- Let Caddy or certbot renew TLS automatically.
- Add uptime and error alerting, so the logging from SEC-07 reaches a person.

## Production readiness for a VPS (SRE review, 2026-10-30)

Independent review of what stands between `main` and a public VPS deployment.
Checked by running `manage.py check --deploy` and `collectstatic` against
`nutrisho.settings.prod` with a throwaway `SECRET_KEY` and `ALLOWED_HOSTS`.
Ordered by priority: **Blocker** means the deployed site will not work or will
lose data without it.

### PR-1 (Blocker): `collectstatic` fails and nothing serves static files when `DEBUG=False`

- `base.py` has no `STATIC_ROOT`, so `manage.py collectstatic` raises
  `ImproperlyConfigured`.
- With `DEBUG=False`, `runserver`/gunicorn do not serve `/static/`, so the
  site renders with no Tailwind CSS, no `style.css` and no HTMX — the app is
  unusable, not just unstyled.
- Fix: set `STATIC_ROOT = env.path("STATIC_ROOT", default=BASE_DIR / "staticfiles")`
  (and git-ignore it), add `whitenoise` with
  `CompressedManifestStaticFilesStorage` (hashed filenames give safe
  long-lived caching), or serve `STATIC_ROOT` from the reverse proxy. Add a
  test that `collectstatic --noinput` succeeds under prod settings.

### PR-2 (Blocker): every POST returns 403 behind a TLS-terminating reverse proxy

- Behind Caddy/nginx terminating HTTPS, Django sees plain HTTP, so
  `request.is_secure()` is False. The CSRF middleware builds the expected
  origin as `http://<host>`, the browser sends `Origin: https://<host>`, and
  every form and HTMX POST fails CSRF. Turning on `SECURE_SSL_REDIRECT` without
  the fix below causes a redirect loop instead.
- `check --deploy` also reports W004 (HSTS), W008 (SSL redirect), W012
  (`SESSION_COOKIE_SECURE`), W016 (`CSRF_COOKIE_SECURE`).
- Fix in `prod.py`: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
  (proxy must set the header and the app must only listen on localhost),
  `CSRF_TRUSTED_ORIGINS` from env, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, and HSTS starting at a short `SECURE_HSTS_SECONDS`
  (e.g. 3600) before raising it. Make all of them env-driven so a local
  prod-settings smoke run still works.

### PR-3 (Blocker): no production server, deployment recipe or runbook

- No WSGI server in dependencies (`gunicorn`/`granian`), no systemd unit, no
  reverse-proxy config, no Dockerfile, no deploy doc. `initial-context.md`
  still says "no production settings, no secrets management".
- VPS-specific traps the runbook must cover:
  - Python is pinned to 3.14, which Debian/Ubuntu LTS do not ship: use
    `uv python install 3.14` + `uv sync --frozen --no-dev`.
  - `output.css` is a git-ignored Tailwind build artifact, so the VPS either
    needs Node + pnpm or CSS is built in CI and shipped as part of a release
    artifact. Prefer building in CI so the server needs no Node toolchain.
  - Secrets: `prod.py` reads `.env` from the repo root. Prefer a systemd
    `EnvironmentFile=` owned by root, mode 0600, outside the checkout.
  - Release steps: `uv sync --frozen`, `migrate`, `collectstatic`, restart
    service, smoke-check.
- Fix: add `gunicorn` (or `granian`) to runtime deps, commit
  `deploy/nutrisho.service`, `deploy/Caddyfile` (Caddy gives automatic TLS
  certificates), and `docs/deployment.md` with the steps above.

### PR-4 (Blocker): no backups that would survive losing the VPS

- `backup_db` writes the dump into `docs/` inside the code checkout, builds the
  whole dump as one in-memory string, has no rotation, and is manual. A lost
  or rebuilt VPS loses every recipe.
- The SQLite file defaults to `BASE_DIR/db.sqlite3`, i.e. inside the git
  checkout, where a careless `git clean -fdx` or redeploy-by-reclone deletes
  it.
- Fix: put the DB outside the checkout via `DATABASE_URL`
  (e.g. `sqlite:////var/lib/nutrisho/db.sqlite3`); schedule a consistent online
  backup (`sqlite3 db ".backup …"` or Python's `Connection.backup()`, not a
  file copy of a live DB) via a systemd timer, with retention, and ship it
  off-box (restic/rclone to object storage, or Litestream for continuous
  replication). Document and test a restore once.

### PR-5 (High): SQLite is not tuned for a multi-worker server

- Default SQLite settings (rollback journal, deferred transactions, 5 s
  timeout) give intermittent `database is locked` errors as soon as two
  gunicorn workers write at the same time — likely with the many small HTMX
  saves this UI makes.
- Fix (Django ≥ 5.1 supports these): in `DATABASES["default"]["OPTIONS"]` set
  `"transaction_mode": "IMMEDIATE"`, `"timeout": 20`, and an `init_command`
  with `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`. Apply only when
  the engine is SQLite. Keeps SQLite viable on a small VPS without moving to
  Postgres.

### PR-6 (High): server errors are silently discarded in production

- There is no `LOGGING` setting. Django's default only logs to the console
  when `DEBUG=True`; with `DEBUG=False` errors go to `mail_admins`, but there
  are no `ADMINS` and no email backend. A 500 on the VPS leaves no traceback
  anywhere.
- Fix: add a `LOGGING` config in `base.py` sending `django` and `recipes`
  loggers to stderr at INFO/WARNING (journald collects it under systemd),
  with `LOG_LEVEL` from env. Optionally add Sentry (free tier) via
  `SENTRY_DSN`, only initialised when set.

### PR-7 (High): poe tasks force dev settings, and `createsuperuser` sets the password "fritz"

- `.poe.toml` sets `DJANGO_SETTINGS_MODULE = "nutrisho.settings.dev"` for
  every task. On the VPS, `uv run poe migrate` or `uv run poe backup` would
  run with `DEBUG=True` and the debug toolbar loaded, and
  `uv run poe createsuperuser` creates superuser `fritz` with password
  `fritz` against whatever `DATABASE_URL` the `.env` points at.
- Fix: let tasks respect an already-set `DJANGO_SETTINGS_MODULE` (or move the
  dev default into the individual dev tasks), make `createsuperuser` prompt
  or read `DJANGO_SUPERUSER_PASSWORD` from the environment, and document that
  ops commands on the VPS use `manage.py` (which already defaults to prod).

### PR-8 (Medium): no brute-force protection on public login forms

- `/accounts/login/` and `/admin/login/` accept unlimited attempts. On a
  public IP these get scanned within hours.
- Fix: `django-axes` (lockout per user+IP) or fail2ban on the proxy access
  log; consider moving admin off `/admin/` via an env-configured path.

### PR-9 (Medium): CI does not check deploy-critical things

- CI runs tests with test settings only, so PR-1/PR-2 regressions and
  missing migrations would not be caught.
- Fix: add CI steps with prod settings and dummy env:
  `manage.py check --deploy --fail-level WARNING`,
  `manage.py makemigrations --check --dry-run`, and
  `manage.py collectstatic --noinput`. Add `.github/dependabot.yml` for the
  `uv`, `npm` (pnpm) and `github-actions` ecosystems so security fixes to
  Django and friends arrive as PRs.

### PR-10 (Medium): unused and dev-only packages in runtime dependencies

- `google-genai` is a runtime dependency but nothing in `src/` or `scripts/`
  imports it. It pulls in a large tree (google-auth, httpx, pydantic, …)
  that becomes attack and upgrade surface on the server.
- `django-debug-toolbar` is a runtime dependency although only `dev.py`
  uses it.
- Fix: drop `google-genai`; move `django-debug-toolbar` to the `dev` group
  so `uv sync --no-dev` on the VPS installs neither.

### PR-11 (Medium): page loads fonts from Google Fonts

- `base.html` loads Inconsolata and Lobster from `fonts.googleapis.com`,
  which sends every visitor's IP to Google. For a site hosted and used in the
  EU this has been ruled a GDPR violation (LG München I, 3 O 17493/20), and it
  is also an external runtime dependency.
- Fix: self-host the two fonts as static files (`@font-face` in
  `style.css`), which also lets a strict `Content-Security-Policy`
  (`default-src 'self'`) be added later.

### PR-12 (Medium): no health endpoint or uptime monitoring

- Nothing to point an uptime checker or the deploy smoke-check at; `/`
  redirects to login.
- Fix: add an unauthenticated `GET /healthz` that runs `SELECT 1` and returns
  200/503, exclude it from login enforcement, and point a free external
  monitor (e.g. UptimeRobot, healthchecks.io for the backup timer) at it.

### PR-13 (Medium, before adding a second account): any user can merge or delete shared ingredients

- Ingredients are global, and the ingredient manager
  (`/recipes/ingredients/manage/…`) only requires login. Merge and plural-merge
  rewrite ingredient references in every user's recipes. Fine while the VPS has
  one account; once there is a second, one user can change everyone's recipes.
- Fix: restrict the manager views to `is_staff` (or a permission) and test
  that a non-staff user gets 403.

---

## Confidence & correctness assessment (QA, 2026-10-30)

Independent test-engineering pass with the VPS move in mind. Everything below
was reproduced, not inferred, unless it says otherwise.

**What is already solid.** 764 tests pass in ~10 s with 97% branch coverage.
The suite is order-independent (reversed and three random orders all green).
Running with pytest-django's `--fail-on-template-vars` finds zero undefined
template variables. `makemigrations --check` is clean, `docs/schema.sql` matches
a freshly migrated database, every `hx-target` / `HX-Retarget` id resolves to an
element in the templates, and the HTML sanitizer resisted the XSS probes tried.
A manual Playwright run against `runserver` showed steps (move, merge, split,
add) and groups/ingredients (add) working and persisting across a reload.

The gaps are in what the suite *cannot* see: real concurrency, case-insensitive
data, the browser glue, and a couple of behaviours the tests pin as correct.

### QA-1 — Concurrent requests fail with "database is locked" (High)

**Evidence.** 8 threads × 15 step move-up/down POSTs against `runserver` on a
file-backed SQLite DB: **57 of 120 requests returned 500**, all
`OperationalError: database is locked`. With the same load and
`OPTIONS = {"transaction_mode": "IMMEDIATE", "timeout": 20}` plus WAL
(`init_command: "PRAGMA journal_mode=WAL;"`): 0 errors in 360 requests (8 and
16 threads).

**Why.** Django opens SQLite transactions as `DEFERRED`. Every mutating view
reads first (`select_for_update`, which is a no-op on SQLite) and then writes, so
two concurrent requests deadlock on the read→write lock upgrade and SQLite fails
one immediately; the busy timeout does not help in that case. On a VPS with
several gunicorn workers, or one browser firing two HTMX requests, users will
hit this. The tests use a single in-memory connection, so they cannot catch it.
The many "row vanished under us" branches in the views (most of the uncovered
lines in `recipe_ingredients.py`) are defending against races the database
setup does not actually serialize.

**Fix.** Set `transaction_mode: "IMMEDIATE"`, a `timeout`, and WAL in
`base.py`'s `DATABASES["default"]["OPTIONS"]` (Django ≥ 5.1). Add a regression
test against a file-backed DB (`transactional_db` plus a `ThreadPoolExecutor`
with one connection per thread, or `live_server`) that fires concurrent moves
and asserts no 500s and a contiguous `index_in_sequence`.

### QA-2 — Typing an existing ingredient in a different case crashes (High)

**Evidence.** With `onion` in the DB, creating an ingredient row named `Onion`
returns **500** (`IntegrityError` on `ingredient_name_ci_unique`). Phones
auto-capitalise the first letter, so this will be common.

**Why.** `IngredientInRecipeForm.save`, `resolve_pending_ingredient` and
`recipe_ingredient_create` all call
`Ingredient.objects.get_or_create(ingredient_name=name)`, an exact,
case-sensitive match, while the DB enforces case-insensitive uniqueness. Edit
and save have the same path. `Cuisine` uses the same pattern without a
constraint, so `Italian` and `italian` silently become two cuisines (reproduced).

**Fix.** One helper that looks up `ingredient_name__iexact` first and only then
creates, used by all three call sites, and the same for `Cuisine`. Tests:
create and save with `Onion` when `onion` exists reuse the existing row; same
for cuisine.

### QA-3 — Sanitizer truncates text after a stray `<` (Medium)

**Evidence** (`safe_step_html`; title and blurb share the code):

| stored text | rendered |
|---|---|
| `Bake (oven<gas 4) for 20 min. Rest.` | `Bake (oven` |
| `Mix until temp<a few degrees. Then serve hot.` | `Mix until temp` |
| `a<b` | `a` |

The DB keeps the full text and the edit form shows it, so the page and the
editor disagree with no hint why.

**Why.** `HTMLParser` treats `<letter…` as the start of a tag. With no closing
`>` it holds the rest in its buffer, and `close()` throws that buffer away.

**Fix.** In `_InlineHtmlSanitizer.result()`, emit any unparsed remainder as
escaped text before closing. Add the rows above as tests, plus a property-style
test: for input with no allowed tags, the visible text (after unescaping) is
unchanged.

### QA-4 — Scaling desyncs servings from quantities and loses data (Medium)

**Evidence.**
- servings 4 × 0.1 → servings clamped to **1**, quantities scaled ×0.1
  (amounts for 0.4 servings). `test_scale_down_sub_half_result_clamps_to_1`
  asserts this as correct.
- servings 3 × 0.5 → servings rounds to 2, quantities are for 1.5.
- Quantities are rounded to 0.01 and **persisted**, so a small multiplier zeroes
  them for good (1 × 0.001 → `0.00`, shown as "0 pinch"), and ×0.3 followed by
  ×3.333 does not get the original back.

**Fix.** Scale quantities by the *effective* ratio (`new_serves / old_serves`
after rounding), so the page always describes the servings it shows. Return a
422 when a non-zero quantity would round to zero. Update the test that pins the
current behaviour.

### QA-5 — HTMX failures are silent (Medium)

The `htmx-config` in `base.html` maps every non-2xx/422 response to
`swap: false, error: true`, and nothing listens for `htmx:responseError`,
`htmx:sendError` or `htmx:timeout`. A 500, a 404, a dropped connection or a
restart mid-deploy leaves the UI unchanged, so the user believes the edit
saved. This happened during the QA-1 stress run: the failed clicks simply did
nothing. **Fix.** Add a global listener that shows a dismissible "Your change was
not saved" banner, and cover it in the browser tests (QA-6).

### QA-6 — No browser tests for the HTMX/JS glue (Medium)

About 25 inline handlers carry real logic: the DOM-position calculation for
inserts (`hx-on::config-request` in the step, ingredient and group edit
partials), the split-at-cursor offset (code points, LF newlines), bulk-select
panel state, panel toggles, and the response-handling config. The Django tests
post hand-written parameters, so drift between the JS and the views' contract
goes unnoticed. The manual run found no breakage today, but nothing keeps it
that way. **Fix.** `pytest-playwright` with `live_server`, running 4–5 journeys
in CI on Chromium: login; add/edit/move/split/merge/bulk-delete steps; add a
group and ingredients; scale; one ingredient-tool merge. The CI job needs to
build `output.css` first or ignore its 404.

### QA-7 — CI doesn't enforce the cheap invariants (Low)

Each of these passes today and costs seconds; together they make sure it stays
that way:
- `manage.py makemigrations --check --dry-run`, so a model change without a
  migration fails.
- A `docs/schema.sql` drift check: migrate a temp DB, run
  `backup_db --schema-only --schema <tmp>`, diff. AGENTS.md requires this file
  to be regenerated, but nothing checks it.
- `--fail-on-template-vars` in pytest `addopts`. There are zero undefined
  variables today, and a typo'd `{{ var }}` currently renders as empty.
- `[tool.coverage.run] branch = true` (97% today) behind the existing 95% gate.

### QA-8 — Backup restore is never exercised (Low)

The README calls the dump the only copy of the data, but no test restores one.
A manual round-trip today worked (dump, then `executescript` into a fresh DB:
all 19 tables identical, `integrity_check` ok). **Fix.** Add that round-trip as a
test. For the VPS, note that `iterdump()` reads table by table and, as far as I
can tell, is not wrapped in a read transaction, so a dump taken while the app
writes may be inconsistent across tables. sqlite3's online backup API
(`connection.backup()`) gives a consistent snapshot.

### QA-9 — Anyone logged in can rewrite every user's ingredients (Low now, High multi-user)

The ingredient tool is behind login only, but its rename, merge and delete
actions change the global `Ingredient` rows, and with them other owners'
recipes. The tests confirm only that login is needed. The design accepts this,
which is fine for one user and becomes a data-integrity risk once the VPS has a
second account. **Fix.** Gate the tool on `is_staff` (or a permission) and add 403
tests for a non-staff user. This may duplicate a security finding.

---

## Performance / efficiency assessment (2026-10-30)

Independent pass by a performance reviewer, with the planned move to a VPS in
mind. Numbers below were measured, not estimated: a throwaway pytest file seeded
recipes of three sizes and counted queries per request with
`CaptureQueriesContext` (in-memory SQLite, test settings), then was deleted.

What is already fine and needs no work: the recipe page is a constant 10
queries regardless of size (the `Prefetch` in `views/recipe.py` does its job),
the home list is 3, `recipe_scale` already uses `bulk_update`, and the template
loader is cached outside DEBUG. Absolute timings are small today (tens of ms),
so the items below are about how cost scales and about the VPS runtime, not
about a slow app right now.

### PERF-1 — SQLite runs DEFERRED transactions: concurrent writes fail instantly with "database is locked" (high, VPS)

`DATABASES["default"]` is SQLite with no `OPTIONS`, so Django opens every
`transaction.atomic()` as `BEGIN DEFERRED`. Almost every write path in the app
reads first (`select_for_update()` is a no-op on SQLite, so it is a plain read)
and writes second: `insert_at_index`, `move_in_sequence`, `remove_and_compact`,
`recipe_ingredient_reassign`, `recipe_scale`, the field/metadata saves. When two
such transactions overlap, the second one cannot upgrade its read lock to a
write lock and SQLite returns `SQLITE_BUSY` **immediately**, without honouring
the busy timeout, because waiting would deadlock. Under gunicorn/uvicorn with
more than one worker or thread, that is a 500 on an ordinary double-click on ↑,
or two HTMX requests in flight at once.

Reproduced outside Django with two connections doing read-then-write:

| mode | result for the second writer |
|---|---|
| `DEFERRED`, rollback journal (current) | `database is locked` after 0.00 s |
| `DEFERRED`, WAL | `database is locked` after 0.00 s |
| `IMMEDIATE`, WAL | waits on `BEGIN` up to the timeout, then proceeds once the first commits |

The code comments assume "SQLite's single-writer locking serializes anyway"
(`utils/sequencing.py`); that is only true with `IMMEDIATE`.

**Proposal.** In the settings used on the VPS (Django ≥ 5.1 supports both keys):

```python
DATABASES["default"]["OPTIONS"] = {
    "transaction_mode": "IMMEDIATE",
    "timeout": 5,
    "init_command": (
        "PRAGMA journal_mode=WAL;"
        "PRAGMA synchronous=NORMAL;"
        "PRAGMA busy_timeout=5000;"
    ),
}
```

WAL also lets reads proceed while a write is in progress, and
`synchronous=NORMAL` is the standard safe pairing with WAL (no corruption on
power loss, at most the last transaction lost). Only apply when the engine is
SQLite, since `env.db()` may later point at Postgres. Add a test that the
options are present, and note the WAL `-wal`/`-shm` side files in the backup
procedure (`backup_db` should use SQLite's backup API or `VACUUM INTO`, not a
file copy).

### PERF-2 — N+1 queries whenever a mutation re-renders a group or the preview pane (medium)

The recipe page prefetches groups, rows and ingredients, but the HTMX endpoints
that re-render the same partials after a mutation pass a bare `Recipe` (or
`IngredientGroup`) fetched with `get_object_or_404`. `_groups_list.html` and
`_iir_list.html` then run one query per group for `group.ingredient.all` and
one per row for `iir.ingredient` (via `display_ingredient_name`). The column-4
preview in the ingredient clean-up tool has the same problem plus one more
query per row for `iir.substitute`.

Queries per request, by recipe size (groups × rows per group, steps):

| endpoint | 1×5, 5 | 3×10, 12 | 6×20, 30 |
|---|---|---|---|
| recipe page (reference) | 10 | 10 | 10 |
| `group_move_up/down` | 15 | 45 | 138 |
| `ingredient_reassign` (1 row → new group) | 29 | 61 | 164 |
| `ingredient_move_up/down` | 19 | 24 | 34 |
| `ingredient_manage_preview` | 16 | 68 | 251 |

Affected call sites: every `render(..., "_groups_list.html", {"recipe": recipe})`
and `_iir_list.html` render in `views/recipe_ingredients.py`, `_group_block.html`
in `recipe_group_create`, and `ingredient_manage_preview` / `_matches_context`
in `views/ingredient_admin.py`.

**Proposal.** One helper next to the recipe view, e.g.
`recipe_with_contents(recipe_id, owner)`, holding the existing `Prefetch`
(extended with `select_related("ingredient", "substitute")`), and use it for
every render that walks groups or rows. For `_iir_list.html`, prefetch on the
group (`group.ingredient.select_related("ingredient")`). Lock in the win with
`django_assert_num_queries` tests that seed two sizes and assert the count does
not grow with size. Matters more if the database later moves to Postgres, where
each query is a network round-trip rather than an in-process call.

### PERF-3 — `recipe_duplicate` issues one INSERT per child row plus two lazy FK loads per ingredient (medium-low)

Duplicating a 6×20-ingredient, 30-step recipe takes 414 queries inside one
transaction (34 for the smallest seed), all while holding SQLite's single write
lock. Each step and each `IngredientInRecipe` is a separate `create()`, and
`ingredient=iir.ingredient, substitute=iir.substitute` loads both related
`Ingredient` rows just to copy their ids.

**Proposal.** Copy by id (`ingredient_id=iir.ingredient_id`,
`substitute_id=iir.substitute_id`) and use `bulk_create` for steps and for each
group's rows (groups need their new pk first, which `bulk_create` returns on
SQLite and Postgres). That brings it to a handful of queries independent of
size. While there: the step copy does not pass `step_title`, so duplicates
silently lose step titles (a correctness bug, found incidentally; it needs its
own test).

### PERF-4 — Response size grows with the whole ingredient table, and nothing is compressed (low-medium, grows with data)

- Every inline ingredient edit and every "+ Add ingredient" ships the full
  `Ingredient` name list as a `<datalist>` (`_all_ingredient_names()`). Measured
  with 2,000 ingredients: **114 KB per click**, for one form field.
- The clean-up tool's column 2 renders every ingredient, unpaginated: **597 KB**
  for the page at 2,000 ingredients, and each search keystroke re-renders the
  column.
- There is no compression anywhere: no `GZipMiddleware`, and no reverse proxy
  is configured yet. That HTML is very repetitive and would shrink about 10×.

**Proposal.** First, enable gzip/zstd on the VPS reverse proxy (Caddy or nginx)
for `text/html`, `text/css` and `application/javascript`. That is a config line
with the biggest effect and no code change. Then, if the ingredient table keeps
growing, replace the datalist with a small autocomplete endpoint
(`hx-get` with `hx-trigger="input changed delay:200ms"`, returning the top 20
`istartswith`/`icontains` matches). Column 2 can stay unpaginated until a real
ingredient count makes it hurt.

### PERF-5 — Static assets are not cacheable, and fonts block first render (low)

- `STATIC_ROOT` and a hashed storage backend are not configured, so filenames
  never change (`style.css`, `output.css`). Browsers have to revalidate every
  asset on each full page load, and a far-future `Cache-Control` cannot be set
  safely. Use `ManifestStaticFilesStorage` (or WhiteNoise's
  `CompressedManifestStaticFilesStorage`, which also pre-compresses) and serve
  `/static/` with `Cache-Control: public, max-age=31536000, immutable`.
- `base.html` loads Google Fonts through the legacy `css?family=` endpoint: a
  render-blocking, third-party stylesheet on every full page load, for two
  fonts (Lobster for headings, Inconsolata for steps) and without
  `display=swap`. Self-host the two `woff2` files under `static/`, declare them
  with `@font-face { font-display: swap; }`, and `<link rel="preload">` them.
  That removes two extra origins (DNS, TLS) from first paint and keeps the app
  independent of Google's CDN. `hx-boost` already avoids re-fetching head assets
  between pages, so this only affects first load and hard refreshes, hence the
  low priority.


---

## Developer experience review (2026-10-30)

Walked through onboarding as a new contributor on a clean checkout: Developer
Guide first-time setup, database, running the app, `uv run poe qa`. Everything
below was reproduced, not inferred. QA itself is in good shape (764 tests,
~98% coverage, ~14 s end to end).

### DX-1 (high) — Following the Developer Guide, you cannot log in

Every view is behind `login_required`, but the guide's only user step is
`python manage.py addinitialuser`, which runs `User.objects.create(username="gotofritz")`
with no password. That user can never authenticate, so a new contributor hits
the login page and stops. Its `help` text also says "Adds a single recipe".

The path that does work, `uv run poe createsuperuser`, is undocumented and
hard-codes the owner's username, email and the password `fritz`.

**Fix:** delete `addinitialuser`; have `poe createsuperuser` read
`DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD` from `.env` (add placeholders to
`.env.example`) or prompt interactively; put `uv run poe migrate` and
`uv run poe createsuperuser` in the guide's *First-time setup*.

### DX-2 (high) — `manage.py` defaults to production settings, and the docs say to use it

`manage.py` does `setdefault("DJANGO_SETTINGS_MODULE", "nutrisho.settings.prod")`.
Only `poe` tasks get dev settings (via `[env]` in `.poe.toml`). Yet the docs tell
contributors to call it directly: the Developer Guide (`python manage.py
addinitialuser`, `delete_recipe`), README (`python manage.py
find_ingredient_duplicates`) and AGENTS.md (`uv run python manage.py migrate` /
`backup_db --schema-only`). Verified on a clean checkout:

- no `.env` yet → `ImproperlyConfigured: Set the SECRET_KEY environment variable`
- with `.env` → `manage.py runserver` serves pages but
  `/static/css/output.css` is a 404 (DEBUG off), so the app is unstyled and the
  debug toolbar missing, with no hint why

The bare `python` in the guide and README also contradicts AGENTS.md's
"never invoke a bare `python`".

**Fix:** add a passthrough `poe manage` task (`python manage.py`, inheriting the
dev `[env]`) and route every documented command through `uv run poe ...`.
Keeping `manage.py` on prod is the safer default for deploys; if it is switched
to dev instead, deploy docs must set `DJANGO_SETTINGS_MODULE` explicitly.

### DX-3 (medium) — `poe test <path>` always fails, and its output buries failures

The task's help says extra args pass through, but `--cov-fail-under=95` applies
to whatever subset you ran: `uv run poe test tests/recipes/test_pluralise.py`
passes 21/21 and then reports `FAIL Required test coverage of 95% not reached.
Total coverage: 14.42%`. So the red→green TDD loop AGENTS.md mandates can't use
the documented test task. Separately, `-vv -s` prints every test id plus the
full migration log (~800 lines), pushing a failure off-screen.

**Fix:** split into `test` (plain `pytest`, args pass through) and `test-cov`
(coverage + threshold) used by `qa`; drop `-vv -s` from the default.

### DX-4 (medium) — Contribution conventions are stale or not enforced

- `docs/developer-guide.md` *Branches and commits* still says
  `feature/<name>` / `fix/<name>`, the form AGENTS.md calls retired.
- Commit-message format (commitizen) and `qa` are enforced only by pre-commit,
  but no doc says to run `uv run pre-commit install`. Without it nothing checks
  commits locally, and CI never checks them either.
- PRs are squash-merged, so the PR title becomes the `main` subject, yet AGENTS.md
  admits "getting it right is manual".

**Fix:** update the guide's branch section to match AGENTS.md, add
`uv run pre-commit install` to *First-time setup*, and add a CI job that lints
the PR title against Conventional Commits.

### DX-5 (medium) — Committed Claude Code config imposes personal tooling on every contributor

`.claude/settings.json` (committed, so it applies to anyone who opens the repo
in Claude Code) runs a SessionStart hook that switches the contributor's
assistant into "caveman" mode by default (`full`), writes a flag to their
`~/.claude/.caveman-active`, and replaces their status line. Also, `poe qa`
(and so the pre-commit hook and CI) runs `test-hooks`, the caveman scripts'
regression suite. That makes `jq` a hard prerequisite of the app's QA, and is
the only reason CI installs it.

**Fix:** move the caveman hooks and status line to user-level config or a
git-ignored `.claude/settings.local.json`, and take `test-hooks` out of `qa`
(keep it as its own task if the scripts stay). Keep the branch-prompt hook
project-level if wanted.

### DX-6 (low) — AGENTS.md prescribes libraries the code doesn't use

AGENTS.md says CLI: `click`, models: `pydantic`, tests may use `faker`,
`polyfactory`, `pytest-data`. In practice CLIs are Django management commands
(argparse), there is no pydantic code (it is importable only transitively via
`google-genai`), `pytest-data` isn't installed, and `faker`/`polyfactory` are
dev deps no test imports. A contributor or agent following AGENTS.md
literally will add a second CLI or validation style.

**Fix:** align AGENTS.md with actual practice (management commands, plain
pytest fixtures in `conftest.py`) and drop the unused dev deps.

### DX-7 (low) — Unused runtime dependency `google-genai`

Declared in `[project].dependencies` but never imported in `src/`, `tests/` or
`scripts/`. It drags a large transitive tree (`websockets`, `pydantic`, google
auth, ...) into every install. **Fix:** remove it until a feature needs it.

### DX-8 (low) — `poe coverage` is macOS-only

It runs `open htmlcov/index.html`; on Linux it fails with
`Failed to spawn: open`. **Fix:** `python -m webbrowser -t htmlcov/index.html`.

### DX-9 (low) — No demo data for trying features locally

A fresh database is empty. Features like the ingredient clean-up tool (merge,
plural pairs, unused-only) need several recipes with duplicate and plural
ingredients before there is anything to click. Reviewers of UI changes have to
hand-build that each time. **Fix:** a `seed_demo` management command (or
fixture) that creates a user's worth of sample recipes, including a few
deliberate duplicates, exposed as `uv run poe seed`.


---

## User impact assessment (Product Engineer, 2026-10-30)

Scope: what the person using Nutrisho actually experiences — reading, cooking
from, editing and organising recipes — with the planned move to a VPS in mind
(reachable from any device, over a real network). Each finding was checked
against the code on this branch; the two data bugs were reproduced with a
throwaway test against the real views.

### UX-1 · Scaling a recipe permanently rewrites it, and drifts (High)

`recipe_scale` (`src/recipes/views/recipe_crud.py`) does not compute a view: it
writes the multiplied quantities and servings back to the database. Cooking a
4-serving recipe for 2 tonight destroys the 4-serving original. It also loses
precision every time, and decouples servings from quantities:

- quantities are rounded to 0.01 on every scale, servings to a whole number,
  with a floor of 1;
- reproduced: a 1-serving recipe with `0.25 tsp` salt, scaled ×0.5 then ×2,
  ends up **serves 2 with 0.26 tsp** — twice the servings for the same salt.
  Scaled ÷3 then ×3 it ends up at `0.27`;
- the panel asks for a bare "Multiply by" factor, so going from 4 to 6 servings
  means working out 1.5 by hand.

The model docstring already notes quantities are "not normalized to per-serving
amounts", so the persisted multiply is the only scaling there is.

**Fix:** make scaling a display concern — a `?servings=N` (or session) value
the recipe page multiplies by at render time, with the stored recipe untouched
and a "reset" back to the original. Ask for target servings, not a factor.
Keep the persisted rescale, if at all, as an explicit "save as new servings"
action. `display_ingredient_name` already pluralises from the rendered
quantity, so it works unchanged on a computed one.

### UX-2 · Duplicating a recipe drops every step title (High, data loss)

`recipe_duplicate` copies `step_text`, `index_in_sequence`, `duration` and
`extra_info` but not `step_title`. Reproduced: a step titled `Ragu` comes back
from Duplicate with an empty title. Since the step-title backfill moved
headings like `RAGÚ` out of the text into that field, the copy now silently
loses structure the original has. `tests/recipes/test_views_duplicate.py` only
creates untitled steps, so nothing catches it.

**Fix:** copy `step_title`, and add a test that compares every copied field of
`Step` and `IngredientInRecipe` (ideally driven off `_meta.get_fields()` so the
next new column cannot be forgotten the same way).

### UX-3 · Failed saves are silent (High once on a VPS)

`base.html` configures htmx `responseHandling` so that anything other than
2xx/422 is `swap: false, error: true`, and nothing listens for
`htmx:responseError` or `htmx:sendError`. When a save fails, the user sees
nothing at all: the editor stays open (or the click does nothing) and there is
no message. Locally this rarely happens; on a VPS it will:

- network blips or a restarting app server (5xx / no response);
- CSRF failures — the token is baked into `<body hx-headers>` at page load, so
  logging in again in another tab rotates it and every open tab's edits start
  failing with 403;
- a recipe deleted in another tab (404).

The user only finds out later that their edit never landed.

**Fix:** one global handler in `base.html` for `htmx:responseError` and
`htmx:sendError` that shows a visible, dismissible banner ("Couldn't save —
check your connection and try again", with a reload hint on 403), and keep the
edit form open so the typed text is not lost.

### UX-4 · Unusable on a phone or tablet (High once on a VPS)

The recipe page is a fixed-size "card": `.recipe-contents` is `width: 1040px;
height: 18cm`, `.sidebar` is `width: 28%`, and `style.css` has no media
queries at all. The viewport meta tag is set, so a phone renders a 1040px page
and the user pans sideways to read ingredients. The kitchen — phone or tablet
propped on the counter — is exactly where a recipe is read, and a VPS is what
makes those devices able to reach the app.

Compounding it, every step, ingredient and title is click-to-edit with no read
mode: on a touch screen, tapping to scroll or to keep the screen awake opens an
editor.

**Fix:** a responsive layout (single column below ~768px, ingredients above
steps), and a read/cook mode that is the default view, with editing behind an
explicit "Edit" toggle. A cook mode could also keep the screen awake (Wake
Lock API) and let the user tick off ingredients and steps.

### UX-5 · No way to find a recipe except scrolling (Medium)

`home` lists every recipe, newest first, as a bare name plus four buttons. No
search, no filter by cuisine or tag, no pagination. The ingredient clean-up
tool has search; the recipe list — the screen used most — does not. With an
imported collection this gets worse with every recipe, and "what can I cook
with the aubergine in the fridge" cannot be answered at all, even though
`IngredientInRecipe` makes it a single query.

**Fix:** a search box on the list (name, plus ingredient name), reusing the
htmx partial-swap pattern the ingredient tool already uses; cuisine as a filter
once it is visible (see UX-6).

### UX-6 · Data the user stores is never shown (Medium)

The recipe page renders title, steps, servings, ingredients and blurb only.
Stored but never displayed anywhere in the reading view:

- `source_instance` — the URL or book page the recipe came from, entered in
  the metadata panel and then only visible by reopening that panel; the most
  useful link back to the original is not clickable;
- `cuisine` — editable, never shown, so it cannot be browsed by either;
- `IngredientInRecipe.substitute` — the ingredient tool carefully repoints
  substitutes on merge/delete, but the recipe page never says "or use X", and
  the inline ingredient form cannot set one;
- `Step.duration` and `Step.extra_info`;
- tags — no UI shows or edits them at all; only Duplicate touches them.

**Fix:** show source (as a link when it is a URL) and cuisine in the sidebar;
render substitute next to the ingredient and add it to the inline form. Either
surface duration/extra info/tags or decide they are dead fields and drop them,
rather than carrying data nobody can see.

### UX-7 · No log-out, and the entry pages are stubs (Medium once on a VPS)

There is no log-out control anywhere (Django's `LogoutView` needs a POST, and
no template posts to `accounts/logout/`). On a laptop that was fine; on a VPS
reached from other devices, the user cannot sign out of a borrowed or shared
one. Related polish for the same move: `/` serves a hard-coded
`<h1>Nutrisho</h1><a>Recipes</a>` string rather than redirecting to
`/recipes/`, and the login page is the unstyled `form.as_p` with no app chrome.

**Fix:** a log-out button (POST form) in the list header and recipe navbar;
redirect `/` to `/recipes/`; give the login page the base template.

### UX-8 · Destructive actions have no undo (Medium)

Deleting a recipe is one click plus a browser `confirm()` on the list, sitting
between Edit metadata and View; bulk step delete and the ingredient tool's
delete/merge (which rewrite *every* recipe using the ingredient) are equally
final. Backups are a manual `poe backup` run, so a mis-click is only
recoverable if the user happened to back up beforehand and is willing to
restore the whole database (losing everything since).

**Fix:** soft delete for recipes (a `deleted_at` column, hidden from the list,
with a short-lived "Undo" toast and a trash view), and move Delete away from
the frequently used buttons on the list. For the ingredient tool, at minimum
record merges/deletes so they can be reversed. Automated, off-box backups on
the VPS are the safety net under all of this.

### If the app is redesigned

A redesign is planned, which changes the order of the work above but not the
problems.

- **Solve in the design, do not patch first:** UX-4 (responsive layout, read
  mode before edit mode), UX-5 (search), UX-6 (where source, cuisine and
  substitutes live on the page) and UX-7 (log-out, login page). The current
  CSS is a fixed 1040px "index card"; making it responsive now is work the
  redesign throws away.
- **Design decides the interaction, code does the rest regardless:** UX-1 (the
  design asks for target servings and makes clear scaling is temporary; making
  scaling non-destructive is backend work either way), UX-3 (the design defines
  the error banner and saving states; the global htmx error handler is needed
  either way), UX-8 (undo toast or trash view, Delete placement; soft delete is
  a model change).
- **Unaffected, fix now:** UX-2, the step title lost on Duplicate.

Suggested brief: design the **cooking view on a phone or tablet** as the
primary screen and editing as a secondary mode. Include print in the brief,
since `print.css` is written against the current card layout and will break
with a new one.

---

## Open source maintainer review — project health (2026-10-30)

Independent pass over dependencies, supply chain, release process, docs and
onboarding, with the VPS move in mind. Checked on `fix/assessment-2026-10-30`:
`uv run poe test` passes (764 tests, 97.96 % coverage against a 95 % gate),
`main` is protected, lint/type/commit-message checks are wired into pre-commit
and CI. The fundamentals are healthy; the findings below are the gaps.

### OSM-1 — Drop the unused `google-genai` runtime dependency

`google-genai~=1.56` is in `[project].dependencies`, but nothing in `src/`,
`tests/` or `scripts/` imports it. It is a runtime dependency, so it would ship
to the VPS: `uv export --no-dev` lists 32 packages, and only 6 of them
(`django`, `asgiref`, `sqlparse`, `django-environ`, `django-htmx`,
`django-debug-toolbar`) are reachable from what the app actually uses. The rest
(`google-auth`, `httpx`, `requests`, `pydantic`, `tenacity`, `anyio`, …) come in
through `google-genai`. It is also the only route to `certifi`, which
`pip-audit` currently flags (PYSEC-2026-4320, fixed in 2026.10.18).

- **Fix:** `uv remove google-genai`; re-add it in the PR that first uses it.
- **Effort:** minutes. **Impact:** smaller attack surface and image, one fewer
  advisory to chase.

### OSM-2 — Move `django-debug-toolbar` to the dev group

It is a runtime dependency but only `settings/dev.py` and the `DEBUG`-guarded
block in `urls.py` touch it. A `uv sync --no-dev` on the VPS should not install
a debugging tool. It is also two majors behind (6.3 installed, 8.0 latest).

- **Fix:** move it to `[dependency-groups].dev`; keep the `if settings.DEBUG`
  guard in `urls.py`. Bump it while there.

### OSM-3 — No automated dependency or Action updates; Django 6.0 pin needs a plan

There is no `.github/dependabot.yml` (or Renovate config). Today
`uv tree --outdated` shows Django 6.0.8 against 6.1.2, and `pnpm audit` reports
one high advisory in a Tailwind build dependency (`source-map-js` < 1.2.2 via
`@tailwindcss/cli`; build-time only, so low real risk, but nobody is told).
GitHub Actions versions are not tracked either.

`Django ~=6.0.0` blocks 6.1. Django 6.0 is not an LTS release and its security
support ends in April 2027, around when 6.2 LTS lands. A self-hosted app wants
to sit on an LTS and take patch releases promptly.

- **Fix:** add `dependabot.yml` for `uv`, `npm` (pnpm) and `github-actions`,
  weekly, grouped so it is one PR per ecosystem. Widen the pin to `~=6.1` now,
  plan the 6.2 LTS move for spring 2027 and then stay on LTS. Turn on
  Dependabot alerts and private vulnerability reporting in repo settings.

### OSM-4 — Harden the CI workflow

`.github/workflows/ci.yml`:

- No top-level `permissions:` block, so the `qa` job (which runs on PRs) gets
  whatever the repo's default token scope is. Set `permissions: contents: read`
  at the top and keep `contents: write` only on `badge`.
- Actions are pinned to moving tags (`@v4`, `@v5`). `peaceiris/actions-gh-pages`
  is third-party and runs with a write token; pin it (at least) to a commit SHA.
  Dependabot (OSM-3) keeps SHA pins current.
- No `concurrency:` group, so superseded pushes keep running. Add
  `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}`.
- No `timeout-minutes`; a hung test burns the default 6 h.
- `sudo apt-get install -y jq` runs without `apt-get update`, which fails when
  the runner's package index is stale. `jq` is only needed by the `.claude`
  hook regression tests; `jq` is preinstalled on `ubuntu-latest`, so the step
  can probably go.

### OSM-5 — No releases, tags or changelog to deploy from

There are no tags or GitHub releases, `pyproject.toml` has been `0.2.0`
throughout, and `package.json` says `1.0.0`. Once the app runs on a VPS,
"what is deployed?" and "roll back to the previous version" need an answer
other than a commit SHA. `commitizen` is already a dev dependency and every
commit is Conventional, so this is nearly free.

- **Fix:** configure `[tool.commitizen]` (version source `pyproject.toml`,
  `update_changelog_on_bump = true`), cut `v0.3.0` with `cz bump`, and deploy
  tags. Tidy the package metadata while there: `authors` is still the
  `Your Name <you@example.com>` placeholder and the description is "Quick and
  dirty django prototype". Mark `package.json` version as irrelevant (or drop
  it) so there is one version number.

### OSM-6 — `poe createsuperuser` hardcodes a password and would hit the live DB

`.poe.toml` creates user `fritz` with password `fritz`. The task runs with dev
settings, and dev settings use the same default database file
(`BASE_DIR/db.sqlite3`) as prod. Run on the VPS out of habit, it plants a
superuser with a guessable password in the production database.

- **Fix:** drop the hardcoded `DJANGO_SUPERUSER_PASSWORD` and let
  `createsuperuser` prompt (or read the password from the environment), and
  take the username from an argument.

### OSM-7 — First-time setup leaves you unable to log in

The developer guide says a fresh checkout is set up with `migrate` then
`python manage.py addinitialuser`. That command does
`User.objects.create(username="gotofritz")` with no password, so the user can
never authenticate, and every view is behind login. Its `help` text says
"Adds a single recipe (pass it as arg)". It has no test.

- **Fix:** either delete `addinitialuser` and document `createsuperuser`, or
  make it create a user with a password from an argument/env and add a test.

### OSM-8 — Developer docs have drifted from the rules and from Linux

- `docs/developer-guide.md` still documents `feature/<name>` / `fix/<name>`
  branches, which `AGENTS.md` says are retired in favour of
  `[<issue>-]<type>-<slug>`.
- `README.md` and the developer guide use bare `python manage.py …`
  (`find_ingredient_duplicates`, `addinitialuser`, `delete_recipe`). `AGENTS.md`
  forbids that because the system interpreter may be older than 3.14; use
  `uv run python manage.py …`.
- Bare `manage.py` defaults to `nutrisho.settings.prod`, so those documented
  commands silently run with prod settings on a dev box. Fine for the VPS, but
  the docs should say so or route dev commands through `poe`.
- macOS-isms: `brew install jq`, and `poe coverage` runs `open`, which does not
  exist on Linux (the VPS, CI). Use `python -m webbrowser` or drop the task.
- `README.md` "What it does" still lists only browse/view/navigate; inline
  editing, scaling, ingredient clean-up and backups have shipped since.

### OSM-9 — Delete dead scripts flagged for removal

- `scripts/backfill_step_titles.py` says "Throwaway — delete once it has been
  run" and the backfill shipped with #20.
- `scripts/sql_to_edit_recipes_hack/` was marked for deletion in plan 004
  (archived), hardcodes `/Users/fritz/work/...`, deletes rows with raw
  interpolated SQL, and is superseded by `manage.py delete_recipe`.

Dead scripts that write to the database are a hazard once the repo is checked
out on a server. Delete both.

### OSM-10 — Backlog lives in files that disagree with GitHub

Only two GitHub issues are open (#19, #32). Planned work lives in
`docs/plans/` and this file instead, and they have drifted:
`docs/plans/008-ingredient-aliases.md` is "Approved — ready to implement" and
tracks #14, which is closed; plans 005 and 006 are undated drafts with no
issue. That makes "what is next before the VPS move" hard to answer.

- **Fix:** once this file is de-duplicated, turn the items worth doing into
  GitHub issues with a `vps` milestone/label, link plans to open issues, and
  reopen or re-file #14 for aliases (or archive plan 008).

---

## Technical debt and engineering sustainability audit (2026-10-30)

Independent pass focused on what makes the codebase harder or riskier to keep
changing. Baseline at audit time: `ruff`, `ty` and 764 tests all green in ~9 s,
98% reported line coverage, `makemigrations --check` clean, and `docs/schema.sql`
matches a freshly migrated database. The findings below are about the
guard-rails around that health, not about broken code. Ordered by value.

### TD-1. Unused `google-genai` runtime dependency; dev-only toolbar shipped as runtime

- **Evidence:** `google-genai~=1.56` is in `[project].dependencies`, but nothing
  in `src/`, `tests/` or `scripts/` imports it. `uv tree --no-dev` shows it pulls
  in `httpx`, `requests`, `google-auth`, `websockets`, `pydantic`, `tenacity`, …
  — most of the 45 runtime packages. `django-debug-toolbar` is also a runtime
  dependency although only `settings/dev.py` and the `DEBUG` branch of
  `nutrisho/urls.py` use it.
- **Why it matters:** every unused package is attack surface, upgrade churn and
  install time on the VPS, for zero behaviour. It also hides the fact that
  `pydantic` (mandated in `AGENTS.md`) is only present by accident (see TD-9).
- **Fix:** drop `google-genai`; move `django-debug-toolbar` to the `dev`
  dependency group; `uv lock`. Re-add an LLM SDK when a feature actually needs it.

### TD-2. Coverage gate is blind to modules no test imports

- **Evidence:** `src/recipes/management/` and `src/recipes/management/commands/`
  have no `__init__.py`. coverage.py only discovers unexecuted files inside
  packages, so a command no test imports never appears in the report.
  `addinitialuser.py` (0% covered) is missing from the report entirely. Adding
  the two `__init__.py` files makes it show up, and the total drops from 98% to
  97% (verified locally, then reverted).
- **Why it matters:** the `--cov-fail-under=95` gate cannot catch a new,
  completely untested management command — exactly the kind of one-off,
  data-mutating code that most needs a test.
- **Fix:** add the two `__init__.py` files (Django's `startapp` layout has them
  anyway). Consider `branch = true` in `[tool.coverage.run]` while there: the
  views are dense with guard branches that line coverage counts as covered as
  soon as the `if` line runs.

### TD-3. Nothing enforces the migration / `schema.sql` rules in CI

- **Evidence:** `AGENTS.md` requires every migration PR to regenerate
  `docs/schema.sql`, but CI only runs `poe qa` (CSS, lint, types, tests, hook
  tests). There is no `makemigrations --check` and no schema drift check. Both
  happen to be clean today.
- **Why it matters:** a model change without a migration, or a migration
  without the regenerated schema, merges green. The schema file is advertised
  as "current", so silent drift makes it actively misleading.
- **Fix:** add a `poe check-migrations` task (and include it in `qa`) that runs
  `manage.py makemigrations --check --dry-run`, migrates a temp SQLite DB
  (`DATABASE_URL=sqlite:///<tmp>`), runs `backup_db --schema-only --schema <tmp>`
  and `diff`s it against `docs/schema.sql`.

### TD-4. Login and ownership are enforced per route by hand, with no structural test

- **Evidence:** all 50 routes in `recipes/urls.py` are individually wrapped in
  `_lr(...)`; recipe ownership is a hand-written
  `get_object_or_404(Recipe, id=recipe_id, owner=request.user)` repeated 38
  times across the view modules. `test_views_ownership.py` checks 16 hand-picked
  endpoints out of ~40 recipe-scoped ones; no test iterates the URLconf.
- **Why it matters:** both protections are correct today, but each new endpoint
  must remember both. Forgetting `_lr` ships a public endpoint; forgetting
  `owner=` ships an IDOR. Neither would fail any existing test.
- **Fix:** add one parametrised test that walks `get_resolver().url_patterns`
  under `recipes:` and asserts (a) an anonymous request gets the login
  redirect / `HX-Redirect`, (b) a different user gets 404 for every route with a
  `recipe_id` kwarg. Optionally go further: replace `_lr` with a subclass of
  Django's `LoginRequiredMiddleware` whose `handle_no_permission` returns the
  HTMX redirect (opt-out via `@login_not_required` for the login views), and a
  small `owned_recipe(request, recipe_id)` helper for the 38 lookups.

### TD-5. View-layer boilerplate: four lists per endpoint and copy-pasted up/down pairs

- **Evidence:** adding one endpoint means editing the view module, the import
  block and `__all__` in `views/__init__.py`, the import block in `urls.py`, and
  the `path()` entry. Up/down moves are separate views for steps, groups and
  ingredients (6 views, 6 routes); `recipe_ingredient_move_up` and
  `_move_down` are ~30 identical lines differing only in `direction=`,
  including a twice-repeated `HX-Retarget`/`HX-Reswap` block each.
- **Why it matters:** the barrel adds merge-conflict hot spots and busywork to
  every feature, and the duplicated bodies already have to be fixed in pairs.
- **Fix:** have `urls.py` import the view modules
  (`from recipes.views import recipe_steps` → `recipe_steps.recipe_step_edit`)
  and delete the re-export barrel. Collapse each up/down pair into one view
  taking `direction` from the URL (`<str:direction>` constrained to
  `up|down`), keeping the URL names the templates use.

### TD-6. Page-specific JavaScript lives inline in `base.html` and is untested

- **Evidence:** `base.html` carries ~70 lines of inline JS: textarea autosize,
  the steps selection panel (`_syncStepsPanel`, Merge disabled below two), the
  ingredient reassign panel, `panelToggle`. It loads on every page, including
  login. No test executes it — the pytest suite can only assert the markup the
  JS relies on.
- **Why it matters:** each new bulk-action UI adds more global listeners to the
  base template, and regressions in client-side state (panel not hiding, Merge
  enabled with one step) are invisible to CI.
- **Fix:** move the script to `static/js/recipe-editor.js`, loaded only by the
  recipe page. Add a single Playwright smoke test (`pytest-playwright` plus
  `playwright install chromium` in CI; no Node build needed) covering: check one step →
  panel shows, Merge disabled; check two → Merge enabled; Cancel → panel hides.

### TD-7. One-off and legacy tooling that should have been deleted

- **Evidence:**
  - `scripts/backfill_step_titles.py` says "Throwaway — delete once it has been
    run"; issue #20's backfill has shipped.
  - `scripts/sql_to_edit_recipes_hack/` hard-codes
    `/Users/fritz/work/nutrisho-django-prototype/nutrisho/db.sqlite3` and deletes
    via raw SQL, superseded by the `delete_recipe` command and the inline editor.
  - `fix_duplicate_sequences` exists to be run "before applying migration 0007".
  - Migration `0008_sanitize_yaml_filenames` carries ~100 lines of frozen
    sanitising logic for a column that `0016` drops.
  - `.ruff.toml` excludes `src/jobs/migrations`, which does not exist.
- **Why it matters:** dead tooling reads as supported tooling, keeps tests and
  coverage alive for code with no future, and the raw-SQL scripts bypass every
  invariant the app now enforces (sequence compaction, PROTECT FKs).
- **Fix:** delete `scripts/` (both items) and
  `fix_duplicate_sequences` (plus its tests); drop the stale ruff exclude. With
  a single deployment, squash `0001`–`0016` (`squashmigrations`, then remove the
  originals once the VPS has applied the squash) so a fresh install no longer
  runs dead data migrations.

### TD-8. The Claude hook regression test tests a copy of the regexes

- **Evidence:** `.claude/hooks/test-caveman-patterns.sh` defines `ACT`, `NEG`
  and `DEACT` as string literals, duplicating the patterns inline in
  `caveman-mode-tracker.sh` lines 25, 26 and 70. It never sources or extracts
  them. Yet it runs in `poe qa` (and therefore CI and every pre-commit), and is
  why CI installs `jq`.
- **Why it matters:** editing the hook's pattern cannot fail the test, so the
  test only adds runtime and a CI dependency to the app's quality gate.
- **Fix:** move the three patterns into `caveman-config.sh` and source it from
  both scripts, so the test exercises the real values. Alternatively take
  `test-hooks` out of `qa` — assistant tooling is not part of the product.

### TD-9. Project standards and plans have drifted from the code

- **Evidence:**
  - `AGENTS.md` mandates `click` for CLIs and `pydantic` for models; neither is
    imported anywhere (CLIs are Django management commands, models are Django
    models), and `pydantic` is only installed transitively via TD-1.
  - `docs/plans/005-data-model.md` and `006-admin.md` have been "Draft" since
    May with no TDD cycles; 005's "review `quantity` FloatField vs
    DecimalField" is already done (`DecimalField(max_digits=7, decimal_places=2)`).
  - `pyproject.toml` still says `description = "Quick and dirty django
    prototype"` and `authors = [{name = "Your Name", email = "you@example.com"}]`.
- **Why it matters:** contributors (human or agent) follow `AGENTS.md` and the
  active plans literally; stale rules produce code that fights the codebase.
- **Fix:** replace the library rules with what the project actually uses
  (Django management commands, Django forms/models); archive or rewrite 005
  and 006 as concrete plans; fix the package metadata.

### TD-10. No automated dependency updates

- **Evidence:** no `.github/dependabot.yml` or Renovate config. Python deps are
  floor-pinned and frozen by `uv.lock`; Tailwind by `pnpm-lock.yaml`. CI sets
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` to keep older action majors running.
- **Why it matters:** Django security releases, and the action deprecations the
  env var is papering over, only get picked up when someone remembers.
- **Fix:** add `dependabot.yml` with weekly, grouped updates for `uv`, `npm`
  (pnpm lockfile) and `github-actions`; the existing CI gate is strong enough to
  merge them with confidence.

---

## Dependency ecosystem health (Dependency Manager review, 2026-10-30)

Evidence gathered on 2026-10-30 with `uv tree --outdated`, `uv export` +
`pip-audit`, `pnpm audit` and `pnpm outdated` against the committed lockfiles.
Ordered by priority.

### DEP-1 · Remove the unused `google-genai` runtime dependency — high

`google-genai~=1.56` is a production dependency, but nothing in `src/`,
`tests/` or `scripts/` imports it (`grep -rn genai` finds nothing). It is the
largest thing in the runtime tree: of the 32 packages `uv export --no-dev`
installs, about 25 exist only because of it (`httpx`, `requests`,
`google-auth`, `cryptography`, `cffi`, `pydantic`, `websockets`, `tenacity`,
`certifi`, …). It is also the only route to a runtime CVE (see DEP-2:
`certifi`), and its `~=1.56` cap keeps it on 1.x while 2.x is current (2.34).

Fix: `uv remove google-genai`. If an LLM feature is planned, add it back in
that PR, behind the code that uses it, at the current major.

### DEP-2 · Clear the known vulnerabilities in the lockfiles — high

The committed lockfiles currently resolve to versions with published
advisories:

| Package | Locked | Fixed in | Pulled in by | Scope |
| --- | --- | --- | --- | --- |
| `certifi` | 2026.7.22 | 2026.10.19 | `google-genai` → `httpx`/`requests` | runtime |
| `filelock` | 4.0.4 (14 CVEs) | 4.2.1 | `pre-commit` → `virtualenv` | dev |
| `virtualenv` | 21.13.0 (11 CVEs) | 21.14.9 | `pre-commit` | dev |
| `source-map-js` | 1.2.1 (GHSA-68fv-2mgg-jv7q, high) | 1.2.2 | `@tailwindcss/cli` → `@tailwindcss/node` | build |

None need a constraint change. `certifi` disappears with DEP-1; the rest are
lockfile refreshes: `uv lock --upgrade-package filelock --upgrade-package
virtualenv` (or `uv lock --upgrade`) and `pnpm update` (the `^1.2.1` range
already allows 1.2.2). Run `uv run poe qa` after.

### DEP-3 · Add automated dependency updates and a vulnerability check — high

There is no Dependabot or Renovate config and no audit step in CI, which is
how DEP-2 accumulated unnoticed. Four ecosystems drift independently: uv
(`uv.lock`), pnpm (`pnpm-lock.yaml`), GitHub Actions (`ci.yml`) and
pre-commit hook revs (already behind: `pre-commit-hooks` v5.0.0 → v6.0.0,
`toml-sort` v0.24.2 → v0.25.0).

Fix:
- Add `.github/dependabot.yml` with `uv`, `npm` (reads pnpm lockfiles) and
  `github-actions` ecosystems on a weekly schedule, with grouped minor/patch
  updates so it stays to a few PRs a week. Use Renovate instead if pre-commit
  revs should be covered by the same bot; otherwise run
  `pre-commit autoupdate` as part of the same weekly chore.
- Add an audit step to CI, e.g. `uvx pip-audit` over `uv export
  --all-groups --no-hashes` and `pnpm audit --prod=false --audit-level=high`,
  so a new advisory fails the build instead of waiting for someone to look.

### DEP-4 · CI does not verify that `uv.lock` matches `pyproject.toml` — medium

`ci.yml` runs `uv sync --all-groups`. Without `--locked`, uv silently
re-resolves and rewrites the lockfile in the runner when `pyproject.toml`
changed but `uv.lock` was not regenerated, so CI tests a different set of
versions from the one committed and the drift is never reported. The Node
side already does the right thing with `pnpm install --frozen-lockfile`.

Fix: `uv sync --locked --all-groups`.

### DEP-5 · Move `django-debug-toolbar` to the dev group — medium

`django-debug-toolbar ~=6.1` is a runtime dependency, but it is only enabled
in `nutrisho/settings/dev.py`. Production installs carry it for nothing.

Fix: move it to `[dependency-groups] dev`. Change the guard in
`src/nutrisho/urls.py` from `if settings.DEBUG:` to
`if "debug_toolbar" in settings.INSTALLED_APPS:`, so a non-dev settings module
with `DEBUG=True` cannot try to import a package that is not installed. While
there, lift the `~=6.1` cap: it pins to 6.x and 8.0 is current.

### DEP-6 · GitHub Actions are pinned to old majors and patched with a Node 24 override — medium

`ci.yml` uses `actions/checkout@v4`, `actions/setup-python@v5`,
`astral-sh/setup-uv@v5`, `actions/upload-artifact@v4`,
`actions/download-artifact@v4` and `pnpm/action-setup@v4`, and sets
`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` to force those Node 20 actions onto
Node 24. Current majors are checkout v7, setup-python v7, setup-uv v7,
upload-artifact v7, download-artifact v8 and pnpm/action-setup v6, which run on
Node 24 natively. The override is a stopgap that will break once those old
majors stop being compatible.

Fix: bump to the current majors (check each changelog, artifact actions in
particular), drop the env override, and let DEP-3's `github-actions` updates
keep them current.

### DEP-7 · Replace the unmaintained `coverage-badge` in the badge job — low

The `badge` job runs `pip install coverage-badge "setuptools<81"`: the tool
still imports `pkg_resources`, so it needs setuptools held back, and both are
installed unpinned outside the lockfile on every push to `main`. That is an
abandoned dependency kept alive by a workaround, and the one install in CI
that is neither locked nor run through uv.

Fix: use a maintained generator (e.g. `genbadge[coverage]`) via `uvx` with a
pinned version, or drop the dependency and write a shields.io endpoint JSON
from `coverage json` output in a few lines of shell.

### DEP-8 · Plan the move off Django 6.0 before its security support ends — low

`Django ~=6.0.0` locks to 6.0.x (6.0.8). Django 6.1 was released in August
2026 (6.1.2 is current), so 6.0 now gets security fixes only, and those end in
April 2027. The pin is deliberate, but nothing tracks the deadline.

Fix: schedule an upgrade to 6.1 (or straight to 6.2 LTS when it ships in April
2027) before April 2027, running with `-W error::DeprecationWarning` first to
surface removals.

### DEP-9 · Commitizen hook hardcodes `.venv/bin/cz` — low

In `.pre-commit-config.yaml` the `commitizen` hook uses
`entry: .venv/bin/cz` while the `qa` hook uses `uv run poe qa`. The hardcoded
path fails on a fresh clone before `uv sync`, and for anyone using
`UV_PROJECT_ENVIRONMENT` or a venv elsewhere.

Fix: `entry: uv run cz check` to match the `qa` hook.

### DEP-10 · Pin the pnpm version in `package.json` — low

`package.json` has no `packageManager` field; CI asks `pnpm/action-setup` for
"10" (latest 10.x at run time) and developers use whatever is installed, so
lockfile format and build-script settings (`allowBuilds` in
`pnpm-workspace.yaml`) can behave differently between machines.

Fix: add `"packageManager": "pnpm@10.28.0"` (the version in use now) and drop
`version: 10` from the workflow so CI, corepack and developers all read the
same pin.

### DEP-11 · Self-host the Google Fonts — low

`recipes/base.html` loads Inconsolata and Lobster from
`fonts.googleapis.com` on every page. That is the app's only third-party
runtime dependency: pages render with fallback fonts offline or when Google
is blocked, and every visitor's IP is sent to Google, which German courts
have ruled a GDPR violation without consent (LG München I, 2022).

Fix: download the two font files (e.g. via `@fontsource/inconsolata` and
`@fontsource/lobster` through pnpm, or as static files) and serve them from
`static/` with `@font-face` in the Tailwind build.

---

## Agent-readiness findings (2026-10-30)

Assessed by running the repo the way a coding agent would: fresh checkout, no
`.env`, `uv sync --all-groups`, then the commands AGENTS.md and the developer
guide prescribe. The baseline is good: `uv run poe qa` passes in about 16
seconds (764 tests, 97.96% coverage), `docs/schema.sql` matches a freshly
migrated database, and AGENTS.md plus `docs/initial-context.md` explain the
architecture well. The issues below are the places where an agent still gets
stuck, wastes context, or is told two different things.

### AR-1. The "ask which branch" hook fires after every context compaction

`.claude/settings.json` registers the SessionStart hook with matcher `"*"`, and
SessionStart fires on `startup`, `resume`, `clear` **and `compact`**. So every
time a long session auto-compacts, the agent is told mid-task "IMPORTANT: Before
any work, ask the user which git branch to work on … Wait for the answer", and a
well-behaved agent stops and waits. In headless or background runs (CI, cloud
sessions, scheduled jobs) nobody is there to answer, and AGENTS.md repeats the
same instruction, so the run stalls before it starts.

Fix: restrict the branch prompt to `"matcher": "startup"`, and reword it (in the
hook and in AGENTS.md) to "if the user has not named a branch and you are in an
interactive session, ask; otherwise use the branch you were given or an open PR's
branch". Keep the caveman hook on `*` if re-injection after compaction is wanted.

### AR-2. The documented schema-regeneration commands fail on a fresh checkout

AGENTS.md says any migration PR must run
`uv run python manage.py migrate` and `uv run python manage.py backup_db --schema-only`.
`manage.py` defaults `DJANGO_SETTINGS_MODULE` to `nutrisho.settings.prod`, which
requires `SECRET_KEY`. `.env` is git-ignored, so in a fresh agent container both
commands die with `ImproperlyConfigured: Set the SECRET_KEY environment
variable`. The `poe` tasks avoid this (`.poe.toml` sets the dev settings), but
the mandated commands bypass poe. `python manage.py check` and
`makemigrations` fail the same way.

The developer guide and README also use a bare `python manage.py …` four times
(`addinitialuser`, `delete_recipe` ×2, `find_ingredient_duplicates`), which
AGENTS.md forbids because the system interpreter may not be 3.14.

Fix: either default `manage.py` to `nutrisho.settings.dev` (prod deployments set
the variable explicitly anyway), or add poe tasks (`schema`, `manage`) and point
AGENTS.md and the docs at those. Replace every bare `python manage.py` with
`uv run python manage.py` or a poe task.

### AR-3. Nothing checks for missing migrations or schema drift

AGENTS.md makes the agent responsible for creating migrations and regenerating
`docs/schema.sql`, but neither `poe qa` nor CI verifies it. The test database is built
from the migrations, so a forgotten migration only fails a test that happens to
touch the changed column; a new constraint, default, `choices` or `on_delete`
change slips through with a green QA run and a green PR. A stale `schema.sql`
is never caught. Both are currently in sync, so
this is about catching the next slip, not an existing bug.

Fix: add to `qa` (or a test) `manage.py makemigrations --check --dry-run`, and a
check that migrates a temporary SQLite file, runs
`backup_db --schema-only --schema <tmp>` and diffs it against `docs/schema.sql`.
`backup_db` already writes deterministic output, so the diff is stable.

### AR-4. `poe test` floods the agent's context

The `test` task runs `pytest -vv -s`, so every QA run prints one line per test
plus captured output: 870 lines for a passing run today, growing with every
test. Agents read tool output into their context window, so each mandated
`poe qa` costs thousands of tokens to learn "all passed", and real failures are
harder to spot in the noise.

Fix: drop `-vv -s` from the default task (pytest's default `-q`-style summary
still names each failure), and add a `test-verbose` task for humans who want the
long form. Optionally add `--tb=short`.

### AR-5. `poe qa` needs Node, pnpm and network to verify Python-only changes

`qa` starts with `css`, which runs a non-frozen `pnpm install` and a Tailwind
build. No test reads the compiled CSS. An agent that only touched Python must
still have Node and pnpm installed and network access to the npm registry, or
the mandated gate fails before the first lint. The non-frozen install can also
rewrite `pnpm-lock.yaml` as a side effect of "just running the checks".

Fix: use `pnpm install --frozen-lockfile` in `node-install`, and split `qa` into
a Python gate (`lint`, `typecheck`, `test`, `test-hooks`) that AGENTS.md and the
pre-commit hook run, with the CSS build kept in CI and `dev`.

### AR-6. An agent cannot log in to check a UI change

Every page is login-only. The developer guide's bootstrap is
`python manage.py addinitialuser`, which calls `User.objects.create(...)` with no
password, so the account it creates cannot log in. The working path, the
`createsuperuser` poe task (user `fritz`, password `fritz`), is not mentioned in
the developer guide. A fresh database also has no recipes, so even a logged-in
agent sees an empty list and cannot exercise the HTMX editors without first
building data by hand.

Fix: make `addinitialuser` (or a new `seed_demo` command) create a user with a
known dev password and a couple of sample recipes covering groups, substitutes,
plurals and step titles, refuse to run under prod settings, and document it in
the developer guide as the way to get a usable local app.

### AR-7. The developer guide contradicts AGENTS.md on branch names

`docs/developer-guide.md` still says branches are `feature/<name>` /
`fix/<name>`. AGENTS.md says that form is retired in favour of
`[<issue>-]<type>-<slug>`. Agents read both, and whichever they read last wins.

Fix: update the developer guide's "Branches and commits" section to match
AGENTS.md (or link to it instead of restating it).

### AR-8. The TDD skill is not discoverable as a skill

AGENTS.md points at `.claude/skills/tdd.md`, which has skill frontmatter, but
Claude Code only discovers skills laid out as `.claude/skills/<name>/SKILL.md`
(as the caveman skills are). The file is only read when an agent follows the
link in AGENTS.md by hand; it never triggers on its own description.

Fix: move it to `.claude/skills/tdd/SKILL.md` and update the AGENTS.md reference.

### AR-9. Hook commands use relative paths

Every hook in `.claude/settings.json` runs `bash .claude/hooks/<script>.sh`
relative to the current directory. If the agent's shell has moved into `src/` or
`tests/`, the UserPromptSubmit hook and the status line fail. Claude Code
provides `$CLAUDE_PROJECT_DIR` for this.

Fix: use `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/<script>.sh"`.

### AR-10. No permission allowlist for the mandated commands

`.claude/settings.json` has no `permissions.allow` block, so in default
permission mode every `uv run poe qa`, `uv run pytest …` and `git commit` the
workflow requires is a prompt. For a repo whose rules require running QA after
each TDD step, that is a lot of interruptions.

Fix: add an allowlist for the read-only and workflow commands (`uv run poe *`,
`uv run pytest *`, `uv run ruff *`, `uv run ty *`, `git status`, `git diff *`,
`git log *`).

### AR-11. Caveman mode is not told to leave documentation alone

The SessionStart hook injects caveman mode into every session. Its Boundaries
section exempts code, commits and PRs, but not documentation. The README is
user-facing and AGENTS.md requires agents to keep `docs/initial-context.md`
current, and both are written in full prose today. An agent following the
injected rules literally will write article-free fragments into them.

Fix: extend the Boundaries line in `.claude/skills/caveman/SKILL.md` (and the
fallback text in `caveman-activate.sh`) to "Code/commits/PRs/docs (`*.md`):
write normal."

### AR-12. This issues list lives where agents read it on every start

AGENTS.md tells agents to read `docs/plans/*.md` first, as active plans. This
file is a review backlog, not a plan, and it breaks the plans' `NNN-` naming.
As several reviews append to it, every agent session pays for it in startup
context, and an agent may treat its findings as work it has been asked to do.

Fix: once triaged, move the findings into GitHub issues or individual numbered
plans, and keep the raw review list out of `docs/plans/` (for example
`docs/reviews/`).

## Architecture and design quality findings (2026-10-30)

Independent review as a staff engineer / Django and DBA, with the planned move
to a VPS in mind. Ordered by severity. ARCH-1 to ARCH-3 were reproduced with a
throwaway test against the current branch; the rest are from reading the code.

### ARCH-1 · Typing an ingredient name in a different case returns a 500 — high

`Ingredient.ingredient_name` is unique case-insensitively
(`ingredient_name_ci_unique`, migration 0013), but every place that resolves a
typed name looks it up case-sensitively:

- `IngredientInRecipeForm.save` (`src/recipes/forms/ingredient_forms.py:36`, `:41`)
- `IngredientInRecipeForm.resolve_pending_ingredient` (`:51`)
- `recipe_ingredient_create` (`src/recipes/views/recipe_ingredients.py:165`),
  which also bypasses the form and repeats the logic a third time

With `onion` in the table, saving an ingredient row as `Onion`, or adding a
new row as `ONION`, misses the existing row, tries to create a new one, hits
the constraint and raises an unhandled `IntegrityError`. Both requests answer
500. The datalist autosuggest makes exact matches likely but does not stop
anyone typing.

Fix: one `resolve_ingredient(name) -> Ingredient` helper (in `services/`) that
does `ingredient_name__iexact` first and creates only on a miss, used by all
three call sites, with tests for the case-variant path. `Cuisine` has the same
case-sensitive `get_or_create` (`src/recipes/forms/field_forms.py:33`, `:53`)
and no case-insensitive constraint, so `Italian` and `italian` silently become
two cuisines; give it the same constraint and helper.

### ARCH-2 · Any signed-in user can rename, merge and delete everyone's ingredients — high (before the VPS)

Recipes are owner-scoped, but `Ingredient` rows are global and the clean-up
tool under `/recipes/ingredients/manage/` only requires a login (no staff or
permission check anywhere in `src/recipes/views/ingredient_admin.py`). A
non-staff second user gets 200 on the manager and can rename, merge or delete
ingredients that live in other people's recipes; `docs/initial-context.md`
even notes that "a delete reaches recipes the current user cannot see".

That is fine while one person uses the app on a laptop. On a public VPS with
more than one account it lets any user rewrite every other user's recipes.

Fix: gate the whole subsystem on a permission (`recipes.change_ingredient` /
`recipes.delete_ingredient`, or `is_staff`) with an HTMX-aware 403, and test
it with the existing `other_user` fixture. If the app is meant to stay
single-user, write that down in `docs/initial-context.md` instead and keep
account creation admin-only.

### ARCH-3 · Duplicating a recipe drops every step title — medium

`recipe_duplicate` (`src/recipes/views/recipe_crud.py:177`) copies steps by
hand-listing `step_text`, `index_in_sequence`, `duration` and `extra_info`.
`Step.step_title` (migration 0015) was added later and never added here, so
the copy loses all its headings. Confirmed: a step titled `Sauce` duplicates
with `step_title == ""`.

The root cause is the pattern, not the one field: every new column on `Step`,
`IngredientGroup` or `IngredientInRecipe` has to be remembered in this view.

Fix: move duplication into a service that copies rows generically (clone the
instance, clear `pk`, reassign the parent, `bulk_create` per level) so new
fields come along by default, and add a test that compares every concrete
field of the original and the copy apart from `id`, the parent FKs and
`recipe_name`.

### ARCH-4 · SQLite is not configured for concurrent writers — high (for the VPS)

`DATABASES` (`src/nutrisho/settings/base.py:64`) is a bare `env.db()` with no
`OPTIONS`, so SQLite runs with Django's defaults: rollback journal, `DEFERRED`
transactions and a 5 s busy timeout. Every mutating view opens
`transaction.atomic()`, reads (the `select_for_update()` calls are no-ops on
SQLite) and then writes. With `DEFERRED`, two such transactions from two
gunicorn workers both take a read lock, and the one that upgrades to a write
lock second can get `database is locked` straight away: to avoid deadlock,
SQLite does not wait out the busy timeout when a read transaction tries to
become a write transaction. The comments in
`utils/sequencing.py` assume "SQLite's single-writer locking serializes
anyway", which is only true with `IMMEDIATE` transactions. Locally, with one
`runserver` process, this never shows.

Fix, in `prod.py` (or `base.py`, the tests use `:memory:`):

```python
DATABASES["default"]["OPTIONS"] = {
    "transaction_mode": "IMMEDIATE",
    "timeout": 20,
    "init_command": (
        "PRAGMA journal_mode=WAL;"
        "PRAGMA synchronous=NORMAL;"
        "PRAGMA foreign_keys=ON;"
    ),
}
```

and point `DATABASE_URL` at a path outside the code checkout (for example
`/var/lib/nutrisho/db.sqlite3`) so a redeploy never touches it. SQLite in WAL
mode is a perfectly good fit for this app on a single VPS; there is no need to
move to Postgres for it.

### ARCH-5 · Scaling rewrites stored quantities and loses data — medium

`recipe_scale` (`src/recipes/views/recipe_crud.py:233`) multiplies and
persists every `IngredientInRecipe.quantity`, rounded to 0.01, and rounds
`servings` to a whole number. Two problems follow from storing the result:

- **Irreversible drift.** `0.25` × 0.5 is stored as `0.13`; scaling back × 2
  gives `0.26`. Small quantities can round to `0.00` and never come back.
  Repeated scaling degrades the only copy of the recipe (the YAML seeds are
  gone, so the database is the source of truth).
- **Servings and quantities disagree.** 3 servings × 0.5 stores `servings = 2`
  (1.5 rounded half-up) next to quantities for 1.5 servings. 1 serving × 0.5
  stores `servings = 1` (clamped) with every quantity halved.

The pluralisation work already established that presentation is computed on
render and the database keeps the canonical form; scaling is the same kind of
thing. Fix: keep the stored quantities as authored and scale at display time
from a requested serving count (query parameter or session), with the
existing `format_quantity` filter doing the rounding on output only. If a
permanent rescale is still wanted, make it an explicit, separate "rewrite this
recipe" action with a warning.

### ARCH-6 · Login is opt-in per URL rather than the default — medium

Authentication is applied by wrapping each route in `_lr(...)`
(`src/recipes/urls.py`), plus a separate `htmx_login_required` on the root
view and a plain `login_required` on `home` (so `home` is wrapped twice). A new
route added without the wrapper is public, and nothing checks for that.

Fix: Django 5.1+ ships `LoginRequiredMiddleware`. Subclass it, override
`handle_no_permission` to return the existing `HX-Redirect` response for HTMX
requests (reuse `_next_param`), and mark the few public views (login, logout)
with `@login_not_required`. Then drop `_lr`, the double decorator on `home`,
and add one test that walks `get_resolver()` and asserts every non-auth route
redirects an anonymous client.

### ARCH-7 · `prod.py` is not a production configuration yet — medium

`src/nutrisho/settings/prod.py` only sets `DEBUG = False`. For a VPS behind a
reverse proxy it is missing:

- `STATIC_ROOT` (so `collectstatic` fails) and a way to serve static files
  (WhiteNoise, or the proxy serving `STATIC_ROOT`); the built
  `css/output.css` is git-ignored, so the deploy also needs the Tailwind build
  step or a CI-built artifact
- `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT` (or the
  proxy doing the redirect)
- `LOGGING` to stdout/journald, so 500s are visible without `DEBUG`
- an application server: nothing in `pyproject.toml` provides gunicorn or
  uvicorn, while `django-debug-toolbar` is a runtime dependency rather than a
  dev one

`docs/initial-context.md` still lists "no production settings, no secrets
management" as a constraint, which the VPS move ends.

Fix: fill in `prod.py`, add `uv run python manage.py check --deploy
--settings=nutrisho.settings.prod --fail-level WARNING` to CI so it stays
filled in, move `django-debug-toolbar` to the dev group, and update the
constraints section of `docs/initial-context.md`.

### ARCH-8 · Backups are a developer tool, not an operational one — medium (for the VPS)

`backup_db` (`src/recipes/management/commands/backup_db.py`) writes the full
dump into `docs/` inside the code checkout, and builds it with
`iterdump()`, which issues one `SELECT` per table outside any explicit
transaction. Against a live database (and with WAL, per ARCH-4) a write
between two of those `SELECT`s yields a dump that is not a consistent
snapshot. There is no schedule, no retention and no off-box copy, and the
database is the only copy of the data.

Fix: keep `--schema-only` as it is for `docs/schema.sql`, but give the data
backup its own path: `VACUUM INTO '<backup dir>/nutrisho-<stamp>.sqlite3'` (or
`sqlite3.Connection.backup()`), which is transactionally consistent and
produces a ready-to-use database file. Run it from a systemd timer or cron on
the VPS, prune old copies, ship them off the box (restic, rclone or the
provider's object storage), and document and test a restore once.

### ARCH-9 · Business logic lives in views outside the ingredient tool — low

The clean-up tool has a proper `services/` layer, and `docs/initial-context.md`
describes services as where the ORM lives. The rest of the app does not follow
it: duplication, scaling, group pruning, ingredient resolution and the
merge/split step operations are all written inline in views
(`recipe_ingredients.py` is 567 lines, `recipe_crud.py` 302). The same "lock
the parent, return 404 if it vanished, `form.save(commit=False)`, save
selected fields" sequence is repeated in most save views. ARCH-1 and ARCH-3
are both bugs that a single shared function would have prevented.

Fix: no big-bang refactor. Move logic into `services/recipes.py` as it is
touched, starting with the two functions ARCH-1 and ARCH-3 need, and keep
views to request parsing, guards and template choice, as the clean-up tool
already does.

### ARCH-10 · Free-text columns are capped at arbitrary lengths — low

`Step.step_text` and `Step.extra_info` are `CharField(max_length=512)`, as is
`Recipe.short_description` (`src/recipes/models/step.py:18`, `:25`,
`recipe.py:29`). SQLite ignores the length, so the cap exists only in forms;
step merge already answers 422 when two steps together pass 512 characters,
and long scraped method text is common. On any other database the column
would reject the longer text.

Fix: make these `TextField`s (on SQLite the migration is a table rebuild with
no data change), keep a generous form-level `max_length` if a limit is still
wanted, and regenerate `docs/schema.sql`.

### ARCH-11 · Model naming and leftover fixture code obscure the schema — low

- Reverse accessors for collections are singular and inconsistent:
  `recipe.step`, `recipe.tag`, `recipe.ingredients_group`,
  `ingredient_group.ingredient` (which yields `IngredientInRecipe` rows, not
  `Ingredient`s), and the `Tag` M2M field is called `recipe`. Templates and
  views read as if they handle one object (`recipe.step.all`). Renaming
  `related_name`s to `steps`, `tags`, `ingredient_groups`, `items` changes no
  SQL, only Python and templates.
- `natural_key()` methods on every model are left over from the removed YAML
  import/export. Only `Recipe` has a matching `get_by_natural_key`; the keys
  on `IngredientGroup` (`group_name`, often `""`) and `Step` (index plus the
  first 32 characters) are not unique, so they could not round-trip anyway.
  Delete them, and their tests, unless fixtures are coming back.
- The project-level root view (`src/nutrisho/urls.py`) is an unstyled inline
  HTML page with one link, which breaks the documented rule that
  `src/nutrisho/` holds configuration only. Replace it with a redirect to
  `recipes:home`.

### ARCH-12 · How far SQLite goes, and when to move off it — info

Not a defect: guidance to keep next to ARCH-4 and ARCH-8 so the move off
SQLite is a decision taken on evidence, not a guess. Figures are orders of
magnitude for a small NVMe VPS, not benchmarks of the actual box.

**Capacity with WAL and the ARCH-4 settings.**

- Reads: readers never block each other or the writer; tens of thousands of
  simple queries a second.
- Writes: one writer at a time, the rest queue. Each click here is a short
  transaction touching a few rows, about 1 ms with `synchronous=NORMAL`, so
  several hundred to a few thousand writes a second before anyone waits.
- Expected load: 10 active users clicking every ~5 s is about 2 writes a
  second. Even 1,000 users would not strain it.
- Size: a recipe is a few KB; 100,000 recipes is a few hundred MB.

**Signals to move.** Usually one of these, not a user count:

1. A second app server, or the database on its own host, is needed. SQLite
   must sit on the app machine's local disk, never on a network volume. This
   is the most common forcing function.
2. Writes queue: `database is locked` errors, or rising p95 latency on save
   endpoints, despite `IMMEDIATE` and a 20 s timeout. As a rule of thumb, start
   planning at a sustained ~50 writes a second.
3. Long write transactions (bulk imports, large merges) block every other
   writer for their whole duration; keep them short or run them off-peak.
4. Features or operations: fuzzy ingredient search (`pg_trgm`), read
   replicas, migrations without a lock (SQLite rebuilds the table, seconds at
   this size).

**Until then.** Keep gunicorn to 2-4 workers, and consider Litestream
(continuous replication of the database to object storage) for
point-in-time recovery, which is the main operational gain Postgres would
otherwise bring. It complements the scheduled backups in ARCH-8.

**What to move to.** Postgres, the best-supported Django backend.

- MySQL/MariaDB: works, but offers nothing over Postgres here and has weaker
  constraint and DDL handling.
- SQLite-compatible distributed options (libSQL/Turso, LiteFS, rqlite,
  dqlite): add replicas but keep a single writer, and their Django backends
  are third-party or thin. Only worth it to keep the SQLite file model.
- Managed Postgres (Neon, Supabase, the VPS provider's own) avoids running it
  yourself; Postgres on the same VPS is equally fine at this scale.

**Cost of the move.** Low: the code already uses `select_for_update` and
portable constraints (`Lower()` unique indexes work on Postgres), so it is
mostly a data copy. Postgres enforces the `max_length` caps SQLite ignores,
so check for over-long text first, or do ARCH-10 before moving.

## Day-to-day correctness (code review, 2026-10-30)

Each finding below was reproduced against the current branch with throwaway
requests through the test client, not inferred from reading alone.

### Typing an existing ingredient in a different case crashes the save (500)

- **Where:** `forms/ingredient_forms.py` (`IngredientInRecipeForm.save`,
  `resolve_pending_ingredient`), `views/recipe_ingredients.py`
  (`recipe_ingredient_create`).
- **What:** the recipe editor resolves the typed name with an exact,
  case-sensitive lookup (`get_or_create(ingredient_name=name)`), while migration
  0013 made names unique case-insensitively (`ingredient_name_ci_unique`). With
  `Onion` stored, adding or editing a row as `onion` misses the lookup, tries to
  insert, hits the constraint, and `get_or_create` re-raises the
  `IntegrityError`. Both `.../ingredients/create/` and `.../ingredients/<id>/save/`
  answer 500. The clean-up tool already compares with `iexact`; the per-recipe
  editor, which is used far more often, does not.
- **Fix:** resolve by `ingredient_name__iexact` and reuse the stored row (keeping
  its canonical spelling) in all three places. Add a test per endpoint.

### Typing a plural recreates the duplicates the clean-up tool removes

- **Where:** same name resolution as above.
- **What:** with `onion` stored, entering `2 onions` creates a new `onions`
  `Ingredient` row. Plan 009 says a plural is a display form and an `onions` row
  is bad data, and "Merge plural" exists to fold such rows back, but the
  everyday input path keeps producing them. Typing the plural is natural when
  the quantity is above one, so this will recur.
- **Fix:** when no row matches the typed name, also match it against existing
  rows' `plural` (rule or override, case-insensitively) and use the singular.
  This is the same "resolve on input" idea as the alias plan (008) and could
  share its lookup.

### Duplicating a recipe drops every step title

- **Where:** `views/recipe_crud.py`, `recipe_duplicate`.
- **What:** the step copy lists `step_text`, `index_in_sequence`, `duration`
  and `extra_info`, but not `step_title` (added in migration 0015). The copy of
  a recipe with "For the stock: …" steps comes back with every heading gone.
  `test_views_duplicate.py` does not check titles, so this went unnoticed.
- **Fix:** copy `step_title`; add an assertion to the duplicate tests. Worth
  copying the model fields generically, so the next new column is not missed
  the same way.

### Scaling is lossy and can permanently zero out quantities

- **Where:** `views/recipe_crud.py`, `recipe_scale`.
- **What:** scaling rewrites stored quantities, rounded to 0.01, and servings,
  rounded to a whole number with a floor of 1. Reproduced on a 1-serving recipe
  with `0.25` of an ingredient:
  - ×0.5 leaves servings at 1 but stores `0.13`, so servings and quantities
    no longer agree;
  - a further ×0.01 stores `0.00`;
  - ×100 then gives 100 servings and still `0.00`. The original amount is gone,
    with no undo.
  Ordinary use drifts too: ×1.5 on 3 servings shows "Serves 5" (4.5 rounded)
  next to quantities scaled for 4.5, and halving then doubling does not return
  the original values.
- **Fix:** prefer scaling at display time (a `?servings=` or multiplier applied
  in the template filter) and leave the stored quantities as the source data.
  If scaling must stay persistent, at least refuse a multiplier that would
  round a non-zero quantity to zero or move servings by something other than
  the multiplier.

### Server errors in HTMX requests are silent outside DEBUG

- **Where:** `templates/recipes/base.html` (`htmx-config` `responseHandling`).
- **What:** every status other than 2xx, 3xx and 422 is set to
  `swap: false, error: true`, and nothing listens for `htmx:responseError` or
  `htmx:sendError`. With `DEBUG=True`, `django_htmx_script` shows the error
  page; with `DEBUG=False` (prod settings), a 403, 404 or 500 does nothing
  visible. The user presses Save, the edit form stays as it was, and nothing
  says the change was not stored. Typical triggers are the 500 above, a CSRF
  failure after logging in again in another tab (the token in `hx-headers` is
  fixed at page render), or the server being down.
- **Fix:** add a small `htmx:responseError` / `htmx:sendError` listener in
  `base.html` that shows a visible "Not saved: <status>, reload the page"
  banner. This needs no server change.

### Deleting a group silently deletes all its ingredients

- **Where:** `templates/recipes/partials/_group_edit.html` (Delete button),
  `views/recipe_ingredients.py`, `recipe_group_delete`.
- **What:** the group's Delete button has no `hx-confirm`, and
  `IngredientInRecipe.ingredient_group` is `on_delete=CASCADE`, so one click
  next to Save/Cancel removes the group and every ingredient row in it, with
  no undo. Recipe delete and bulk step delete both ask first. The view also
  lets the recipe's last group go, although `_prune_empty_group` deliberately
  keeps it.
- **Fix:** add `hx-confirm` naming how many ingredients will go, or refuse to
  delete a non-empty group and point to "Move to" first. Keep the last group,
  as the prune rule does.

### Cuisine names duplicate by case

- **Where:** `forms/field_forms.py`, `RecipeMetadataForm.save`.
- **What:** cuisine is resolved with an exact `get_or_create`, so typing
  `italian` with `Italian` stored creates a second cuisine. This is the same
  variant problem that ingredients solved with migration 0013. It does not
  crash, because `Cuisine.cuisine` is only case-sensitively unique, but the
  datalist grows near-duplicates over time.
- **Fix:** resolve by `cuisine__iexact` and keep the stored spelling.
  Optionally add a `Lower("cuisine")` unique constraint once existing
  duplicates are merged.

### Ingredient substitutes are stored but never shown or editable

- **Where:** `IngredientInRecipe.substitute`,
  `templates/recipes/partials/_ingredient_display.html`, `IngredientInRecipeForm`.
- **What:** the model, the clean-up tool (which carefully repoints
  `substitute` on merge and delete) and the duplicate view all handle
  substitutes, but the recipe page never renders one and the inline form
  cannot set or clear one. Any imported "or use X" information is invisible to
  someone cooking from the page.
- **Fix:** render `(or <substitute>)` in the display partial (and add
  `substitute` to the `select_related` in the `recipe` view). Add an optional
  substitute name field to the inline form, resolved like `ingredient_name`.

---

## Long-term evolution (software architect review, 2026-10-30)

Scope: how well the codebase will absorb the next year or two of change — new
fields, new features, more recipes, possibly more users. Ordered by how much
they cost if left alone.

### LT-1. Duplicating a recipe silently drops step titles (schema drift in hand-written copies)

**Severity: high (data loss, and the pattern will recur).**

`recipe_duplicate` (`src/recipes/views/recipe_crud.py:152`) copies every row
field by field. `Step.step_title` was added in migration 0015 and the copy at
`recipe_crud.py:177` was never updated, so the duplicate loses every step
heading. Verified with a throwaway test: a step titled `RAGU` comes back with
`step_title == ''`. `test_views_duplicate.py` has no step-title case, so CI is
green.

The root cause is structural: each new column has to be remembered in every
place that enumerates fields — the duplicate, the `update_fields` list in
`recipe_metadata_edit`, the clean-up tool's recipe preview. Nothing fails when
one is missed.

Direction: copy model instances generically (clone with `pk=None` and override
the FKs, or iterate `_meta.concrete_fields` and exclude pk/FK), and add a test
that asserts every concrete field of `Step`, `IngredientGroup` and
`IngredientInRecipe` survives a duplicate, so the next migration fails CI
instead of shipping.

### LT-2. Scaling rewrites stored quantities and drifts the servings/quantity ratio

**Severity: high (silent, irreversible data corruption).**

`recipe_scale` (`recipe_crud.py:233`) multiplies and *persists* every
quantity, rounded to 2 dp, while `servings` is rounded to an integer and
clamped at 1 (`recipe_crud.py:251`). The two round independently, so the ratio
the recipe was written for is lost:

- `servings=1`, × 0.5 → servings stays 1, quantities halve. The recipe now
  claims one serving with half the food. `test_scale_down_sub_half_result_clamps_to_1`
  pins this behaviour as correct.
- `servings=5`, × 0.5 → servings 3, quantities for 2.5.
- × ⅓ then × 3 turns `1` into `0.99`; small quantities (`0.05 tsp`) collapse
  to `0.00`/`0.03` after a few rounds.

Every scale compounds the error and there is no undo — the database is the
only copy (README "Backing up").

Direction: make scaling a view-time concern. Keep the stored quantities and
`servings` as authored, and render with a requested serving count
(`?serves=6`, or a session value) through a template filter next to
`format_quantity`. If a persistent "rewrite for N servings" is still wanted,
compute it from the original values rather than from the previous result.
This also unlocks per-serving arithmetic for nutrition later, which the
`Recipe` docstring already flags as blocked.

### LT-3. Decide single-user vs multi-user before more features depend on the answer

**Severity: medium (architectural ambiguity that gets more expensive every feature).**

The model is half multi-tenant. Recipes are owner-scoped (`Recipe.owner`,
unique name per owner, every view filters by `owner=request.user`), but
`Ingredient`, `Cuisine`, `Source` and `Tag` are global, and the clean-up tool
is open to any logged-in user (`views/_auth.py`). Any second account can
rename, merge or delete ingredients inside the first account's recipes — the
delete confirmation even counts recipes "across all owners".

Planned work leans on whichever answer is chosen: plan 008's aliases are a
global table, tags have no owner, and a future import would create global
ingredients.

Direction: write the decision into `docs/initial-context.md`. If the app is
personal, say so and gate the global tools behind `is_staff` so a second login
cannot damage shared data. If multi-user is a goal, introduce per-owner
vocabularies (or a shared canonical list with per-owner overrides) now, while
there is one table of ingredients and no aliases yet.

### LT-4. Domain operations live in views, outside the services boundary

**Severity: medium (blocks reuse by any future API, CLI or import).**

`docs/initial-context.md` sets the boundary — services hold pure query and
mutation functions, views stay thin — but only the clean-up tool follows it.
Duplicate, scale, reassign-between-groups and group pruning are transactional
domain logic written inside view functions (`recipe_crud.py`,
`recipe_ingredients.py`, 567 lines). They cannot be called from a management
command, a future import or an API without an HTTP request, and they are only
testable through the client.

Direction: move them into `recipes/services/` (e.g. `recipe_ops.py`) as each is
next touched, with the views reduced to parse → call → render, matching
`ingredient_admin.py`. No big-bang refactor needed; LT-1 and LT-2 are natural
first candidates.

### LT-5. There is no way to get recipes in except typing them field by field

**Severity: medium (caps how far the collection can grow).**

The YAML import was removed with the seed files (#27). New recipes now come
from "New recipe" plus inline editing, one ingredient and one step per form,
or from the hand-run SQL in `scripts/sql_to_edit_recipes_hack/`. Plan 008
assumes recipes "are scraped from many sources", but no scraper or importer is
in the repo, so the alias work has no input pipeline to hook into.

Direction: one importer behind a service function (LT-4), fed first by the
format most recipe sites already publish — schema.org `Recipe` JSON-LD — or by
pasted plain text (one ingredient per line, one step per paragraph). It is the
natural place to apply plan 008's alias resolution and the step-title
recognition in `utils/step_title.py`.

### LT-6. Dormant schema: columns and models with no way to set or use them

**Severity: low–medium (carrying cost and false signals for future work).**

Several parts of the schema are migrated, copied and backed up, but have no
UI and no reader:

- `Step.duration`, `Step.extra_info` — only touched by the duplicate.
- `Source` (with a self-referential `parent`) — no form sets `Recipe.source`;
  only `source_instance` is editable. Admin only.
- `Tag` — no UI to add, show or filter by tags; only the duplicate copies them.
- `Ingredient.family` and `dietary_constraint` — editable in the clean-up tool
  but never displayed, filtered on, or rolled up to a recipe ("is this
  vegetarian?").
- `Cuisine.cuisine` still has the verbose name `"region.area.subarea just as
  placeholder"`.

Direction: for each, either surface it (tags and cuisine as list filters,
dietary constraint rolled up to the recipe) or drop it in a migration. Keeping
undecided columns means every schema change, duplicate and future import has
to carry them anyway.

### LT-7. Units are free text, which blocks nutrition, shopping lists and conversion

**Severity: low now, high if any of those are on the roadmap.**

`IngredientInRecipe.unit` is a free `CharField`. `g`, `gr`, `grams`, `Tbsp`
and `tablespoon` are all different values, and pluralisation already depends
on "unit is empty" as a proxy for countability. Anything that aggregates
across rows — a shopping list, nutrition per serving (the project is called
Nutrisho), metric/imperial conversion — needs a known unit vocabulary first.

Direction: when (if) any of those features is planned, start with a `Unit`
lookup (canonical name, plural, dimension: mass/volume/count) and a clean-up
pass in the same spirit as the ingredient tool. Doing it before more data
accumulates is much cheaper than after.

### LT-8. Recipe browsing does not scale past a few dozen recipes

**Severity: low–medium.**

The home page lists every recipe newest first, with no search, filter or
pagination (`views/home.py:12`). Prev/next on the detail page walks by `id`
ascending (`views/recipe.py:13`), the opposite direction to the list, and wraps
around. With tags and cuisine dormant (LT-6), the only way to find a recipe is
scrolling.

Direction: a search box on recipe name and ingredient (the clean-up tool's
`search_ingredients` pattern already exists), cuisine/tag filters once LT-6 is
decided, and prev/next following the same ordering as the list.

### LT-9. Leftovers from earlier eras that now mislead

**Severity: low (cleanup).**

- `natural_key()` on every model, and `RecipeManager.get_by_natural_key`, were
  for fixture/YAML serialisation, which is gone. Several are not even unique
  (`IngredientGroup` returns `group_name`, often `""`; `Step` returns a 32-char
  prefix), so they would mislead anyone who tried to rely on them.
- `scripts/sql_to_edit_recipes_hack/` hard-codes `/Users/fritz/...`, writes
  straight to the tables past the sequencing invariants, and is superseded by
  inline editing and `delete_recipe`.
- `docs/plans/005-data-model.md` and `006-admin.md` are drafts that predate
  most of the current code (005 still asks about `FloatField` vs
  `DecimalField`; `quantity` has been a `DecimalField` for a while). They should
  be rewritten against today's model or archived.
- `docs/initial-context.md` says "no production settings", but
  `src/nutrisho/settings/prod.py` exists.

Direction: delete the dead code and scripts, archive or rewrite the stale
plans, and correct the constraint line.

## Accessibility review

Independent accessibility pass, 2026-10-30. Method: read every template, the
stylesheets and the inline scripts; ran the dev server with sample data and
audited home, recipe (with each edit form open), new recipe and the ingredient
manager with axe-core 4.10 (WCAG 2.2 A/AA + best practice, debug toolbar
excluded) in Chromium; walked each page with the keyboard only; checked
reflow at 640 and 320 CSS px. Ordered by impact. WCAG success criteria in
brackets.

### A11Y-1 Inline editing cannot be reached from the keyboard (critical)

[2.1.1 Keyboard, 4.1.2 Name, Role, Value]

Every edit on the recipe page starts from a click on a non-interactive
element: the title, servings and blurb (`<span class="editable">` in
`partials/_field_display.html`), each step (`<span>` in `_step_display.html`),
each ingredient (`<div>` in `_ingredient_display.html`) and each group name
(`<h4>` in `_group_display.html`). None is focusable (`tabIndex` is -1), so a
Tab walk of the recipe page goes from the navbar straight to the step
checkboxes and move buttons and never lands on anything editable. Keyboard and
switch users cannot edit a recipe at all, and screen-reader users get no hint
that the text is editable.

Fix: make the trigger a real `<button type="button">` (styled to look like the
text, or a separate small "Edit" button per row), keeping `hx-get` on it. A
`tabindex="0" role="button"` element with an extra `keyup[key=='Enter']`
trigger also works but needs Space handled too, so the button is simpler. Let
Escape trigger the form's Cancel while we are here.

### A11Y-2 Recipe matches in the ingredient manager are links without `href` (critical)

[2.1.1 Keyboard]

`ingredient_admin/_recipe_matches.html` renders each match as
`<a hx-get=…>` with no `href`. Such an anchor is not focusable: in the
keyboard walk, Tab goes from the last ingredient checkbox past the whole
matches column. Keyboard users cannot open the preview, which is the point of
column 2.

Fix: render each match as `<button type="button">` styled as a link (it loads
a fragment, it does not navigate).

### A11Y-3 Icon-only controls have no accessible name (critical)

[1.1.1 Non-text Content, 2.4.4 Link Purpose, 4.1.2 Name, Role, Value]

- `navbar.html`: the three links (all recipes, next, previous) contain only an
  inline SVG with no title or label. Screen readers announce "link" three
  times, or read the URL.
- `nav_recipe.html`: the edit, scale and delete buttons contain only an SVG.
  The scale icon is an SVG `<text>` "×", so at best it is read as
  "multiplication sign".
- The three sidebar buttons toggle a panel open and shut (`panelToggle`) but
  expose no state.

axe reports these as `link-name` and `button-name` (critical/serious).

Fix: `aria-label` on each link and button ("All recipes", "Next recipe",
"Previous recipe", "Edit recipe details", "Scale recipe", "Delete recipe"),
with a matching `title` for a mouse tooltip; `aria-hidden="true"
focusable="false"` on the included SVGs; `aria-expanded` and `aria-controls`
on the three toggle buttons, updated in `panelToggle` and when the panel is
filled or emptied.

### A11Y-4 Focus is dropped or left behind after HTMX swaps (serious)

[2.4.3 Focus Order, 3.2.2 On Input]

Measured with the keyboard in Chromium:

- Pressing Enter on a step's ↓ button moves the step, but `#steps-list` is
  swapped wholesale and focus falls back to `<body>`. To move a step two
  places the user has to Tab back in from the top of the page. Same for
  ingredient and group move buttons.
- Saving or cancelling the metadata panel empties it and focus goes to
  `<body>`. The same happens for every inline edit form's Save, Cancel and
  Delete.
- Opening the metadata panel with the edit button leaves focus on the button,
  but the panel is injected into `#metadata-panel` in the left column, which
  comes earlier in the DOM than the sidebar. The next Tab goes to the scale
  button; the form is reachable only by Shift+Tabbing back through every step.
- Opening an inline edit form does not move focus into it.
- Boosted navigation (Next/Previous, links from the list) swaps the body and
  leaves focus on `<body>` with no announcement that the page changed.

Fix: put `autofocus` on the first field of each edit/panel form (htmx 2
focuses it after the swap); give each move button a stable `id`
(`step-4-down`), so htmx restores focus to it after the list swap; after Save
or Cancel, focus the display element that replaced the form (needs A11Y-1);
render the metadata panel next to its trigger in the DOM, or focus its first
field; on `htmx:afterSettle` of a boosted request, focus the page's `<h1>`
(with `tabindex="-1"`).

### A11Y-5 Several form controls have no label (serious)

[1.3.1 Info and Relationships, 3.3.2 Labels or Instructions, 4.1.2]

- The step and ingredient selection checkboxes (`.step-select`,
  `.ingredient-select`) have no label. A screen reader hears "checkbox, not
  checked" a dozen times with no way to tell which row it belongs to. axe:
  `label`, critical.
- The manager's select-all checkbox (`_ingredient_count.html`) sits in an
  empty `<label>`; the `title` on the label does not name the input. axe:
  `label`, critical.
- The step edit form (`_step_edit.html`) renders title and text with
  placeholders only ("Title (optional)", "New step"). The placeholder is gone
  as soon as there is text, which is always the case when editing an existing
  step, so nothing says which box is the title.
- The reassign panel's "New group name" input is placeholder-only too.

Fix: `aria-label="Select step 2"` / `aria-label="Select onion"` on the row
checkboxes (number or name from the row), `aria-label="Select all
ingredients"` on select-all, and real labels (visually hidden is fine) for
the step title, step text and new group name.

### A11Y-6 Move buttons are unlabelled arrows and too small to hit (serious)

[2.5.8 Target Size (Minimum), 2.4.6 Headings and Labels]

The ↑/↓ buttons are 15.5×15px (`.move-btns button`, 11px font, 1px/4px
padding) and the row checkboxes are 13×13px, all well under the 24×24px
minimum, packed in a row of three with 2px gaps. axe flags 22 targets on a
three-step, three-ingredient recipe. Their accessible names are the glyphs,
read as "upwards arrow" / "downwards arrow", with no indication of which step
or ingredient they move.

Fix: at least 24×24px hit area (padding, or `min-width`/`min-height`), and an
`aria-label` such as "Move step 2 up" / "Move onion down". Disabling ↑ on the
first row and ↓ on the last would also avoid a no-op request.

### A11Y-7 Status changes and errors are not announced (serious)

[4.1.3 Status Messages, 3.3.1 Error Identification]

Nothing on the site uses a live region, so screen-reader users get no
feedback from any HTMX action:

- the bulk-steps bar appearing with "2 steps selected", and the reassign
  panel appearing when an ingredient is ticked;
- the manager's "N found / N selected" and "N matches / N selected" counts,
  and the "Saved" after an ingredient save;
- `.form-error` messages swapped in after a 422 (group name required, scale
  errors, split errors, merge/delete guard messages);
- a step, ingredient, group or recipe disappearing after Delete.

The hand-rendered `ingredient_name` and `cuisine_name` inputs also bypass
Django's automatic `aria-invalid` / `aria-describedby` on errored fields
(checked: `{{ form.as_p }}` fields get them, these two do not), so their
errors are not tied to the field.

Fix: `role="status"` on the selection counts, the manager counts and
"Saved"; `role="alert"` on `.form-error`; add `aria-invalid` and
`aria-describedby="{{ field.auto_id }}_error"` to the two hand-rendered
inputs when they have errors; a short polite announcement after a delete.

### A11Y-8 Pages have no language, and the root page is not an HTML document (serious)

[3.1.1 Language of Page, 2.4.2 Page Titled]

`base.html` has `<html lang="">`, so every page except login has no
language and screen readers pick a voice by guesswork (axe:
`html-has-lang`, serious). `nutrisho/urls.py` `_root` returns a bare
`<h1>…<a>` fragment with no doctype, `<title>` or `lang`, which is what a
user lands on right after logging in.

Fix: `lang="en"` in `base.html`; have `_root` redirect to `recipes:home` (or
render a template that extends `base.html`).

### A11Y-9 The recipe page has no landmarks or heading outline (moderate)

[1.3.1 Info and Relationships, 2.4.1 Bypass Blocks, 2.4.6 Headings and Labels]

- No page has a `<main>`; the left navbar is a `<div>`, not a `<nav>`.
- The recipe page has no `<h1>`: the title is a `<span>` inside
  `div.recipe-title`. There is no heading for the ingredients or the method,
  "Serves 4" is an `<h3>`, and group names are `<h4>` with no `<h2>` above
  them. A screen-reader user jumping by heading cannot find the method.
- The ingredient manager has no heading at all, and its three columns are
  unlabelled `div`s.

Fix: wrap each page's content in `<main>`; make the navbar
`<nav aria-label="Recipes">`; make the recipe title the page `<h1>` (the
editable trigger from A11Y-1 can sit inside it); add `<h2>` "Ingredients" and
"Method" (visually hidden if the design does not want them); make "Serves"
a `<p>` and group names `<h3>`; give the manager an `<h1>` and `aria-label`s
or headings for its columns.

### A11Y-10 The layout does not reflow, and the fixed navbar covers content when zoomed (moderate)

[1.4.10 Reflow, 1.4.4 Resize Text]

`.recipe-contents` is a fixed `width: 1040px; height: 18cm`, centred, and the
`position: fixed` navbar is 3rem wide. Below about 1136 CSS px of viewport,
which is a 1366px laptop at 125% zoom, the navbar sits on top of the start of
the title and the "+ Add step" button. At 200% zoom on a 1280px screen (640
CSS px) the page scrolls horizontally to 1040px and the navbar covers the
first letters of the title and steps (checked in Chromium, debug toolbar
hidden). All type is in px (body 20px, sidebar 14px, panels 12px, move
buttons 11px), so the browser's default font size setting has no effect.

Fix: `max-width` instead of `width`, stack the sidebar under the method
below a breakpoint, offset the content by the navbar's width
(`padding-left: 3rem` on `body` or the container) so they never overlap, drop
the fixed height on screen, and size type in `rem`. `print.css` already
resets the width for print, so the print layout is unaffected.

### A11Y-11 Edit fields are nearly invisible (moderate)

[1.4.11 Non-text Contrast]

Inline-edit inputs and textareas get `border: 1px dotted silver` on white,
about 1.8:1 against the 3:1 minimum, with `background: inherit` and the same
font as the display text. Once a step or the title switches into edit mode it
is hard to see that it is now a field, or where it ends. The move buttons'
`#ccc` border has the same problem.

Fix: a solid border of at least `#767676` (4.5:1 on white) for inputs and
textareas, and the same for the move buttons.

### A11Y-12 Recipe list actions all have the same names (minor)

[2.4.4 Link Purpose (In Context), 2.4.6 Headings and Labels]

Each row of `home.html` is "Edit metadata", "Delete", "View", "Duplicate",
then the recipe name. In a screen reader's links or buttons list this is
dozens of identical "View" and "Delete" entries, and in reading order the
actions come before the recipe they act on.

Fix: add the recipe name to each action as visually hidden text (e.g.
`View<span class="sr-only"> {{ recipe.recipe_name|striptags }}</span>`), and
put the name first in the DOM (CSS `order` can keep the current visual
layout).
