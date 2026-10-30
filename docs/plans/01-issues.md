
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
