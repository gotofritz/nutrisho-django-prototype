# Plan 012: The recipe clipper extension

## Status: In progress, M1 done (#154)

## What we are building

A browser extension, in `extension/` (#145), that clips a recipe from the
page the user is reading into their Nutrisho.

1. The user selects text on a recipe page and clips it, from the right-click
   menu, a shortcut or the toolbar button.
2. A sidebar opens with the text in a clipboard area. From there it is added
   to the recipe's name, blurb, ingredients or steps, or replaces what is
   there.
3. Each ingredient line becomes a row with the fields it has on the site.
   The sidebar fills in what it recognises and marks the names the library
   does not have. Everything can be edited, as on the site.
4. *Save* sends the recipe to the user's Nutrisho server, and *Open in
   Nutrisho* shows it there.

## How

The extension is [anklipper](https://github.com/gotofritz/anklipper)'s shell
with a recipe where the card was. Each time the sidebar opens it loads the
user's ingredients, units and cuisines from the server, and checks the draft
against them in the browser. A save is one call to the endpoint the server
already has (`POST /recipes/api/recipes/`, #78), carrying a Nutrisho document
(`server/docs/features/import-export.md`) and an id the extension made.

### Pinned decisions

Changing one means editing this list.

- **D1 Stack.** WXT, Svelte 5, strict TypeScript, Vitest and pnpm, at
  anklipper's pinned versions. The code starts as a cut-down copy of
  anklipper.
- **D2 Sidebar.** The UI is a sidebar. A capture starts from the right-click
  menu, a shortcut or the toolbar button: only those let the extension read
  the page (`activeTab`).
- **D3 Clipboard.** Captured text lands in a clipboard area, and from there
  is added to the name, blurb, ingredients or steps, or replaces them. Typed
  or pasted text is treated the same.
- **D4 Lists loaded on open.** As Joplin's clipper does with tags, the
  sidebar loads the user's full lists of ingredients, units and cuisines
  every time it opens, and checks names against them in the browser. A name
  they do not hold is marked *new*.
- **D5 Editing as on the site.** The sidebar edits a draft with the fields
  and rules of the site's recipe editor.
- **D6 Ingredient rows.** A row has the site's fields (quantity, unit,
  ingredient, substitute, preparation, note) plus *rest*. Each line is
  scanned: what is recognised fills a field, and everything else stays in
  *rest* (M7).
- **D7 Group headings.** A line among the ingredients can be made a group
  name.
- **D8 Ids.** A recipe's id is a UUID, made by whoever creates the recipe.
  The extension makes one when a draft starts, so a save sent twice makes
  one recipe. A capture from another page starts a new recipe.
- **D9 Units.** A shared vocabulary like ingredients: a global list curated
  by staff, plus each user's own (M1).
- **D10 API.** Plain JSON endpoints, no GraphQL, signed in by API key only.
  The extension's own pages call them, never a content script.
- **D11 API key.** Kept in `storage.local`; never synced, logged or shown
  again. Made with `create_api_token` until the Config page exists (#150),
  which comes before a release.
- **D12 Long text.** Text too long for its field is refused, never cut, and
  the sidebar names the field.
- **D13 Structure.** Ports and adapters, as in anklipper: the draft and its
  rules are pure TypeScript, `browser.*` is reached only in `platform/`, and
  every port has an in-memory fake for the tests.
- **D14 Permissions.** `activeTab`, `scripting`, `storage`, `contextMenus`
  and the sidebar, plus the server's address as an optional host permission,
  asked for when it is saved. Never `<all_urls>`.
- **D15 Privacy.** Only the draft leaves the browser, only to the user's own
  server, and only when the user saves. Nothing from a page is logged.
- **D16 Quality gates first.** Lint, type check, tests and CI come with the
  first extension PR. After at most two set-up PRs, every PR leaves a
  clipper that can be used.
- **D17 Dev server first.** Built against the local dev server (`http`, on
  loopback only). The server's address is a setting, and a production one is
  added when there is one (#87).
- **D18 Firefox first.** Chrome is built in CI from the start, and becomes a
  release target after the first Firefox release.
- **D19 Look.** The site's storybook look, from its own tokens and
  self-hosted fonts (M12).
- **D20 Models.** Any model is the user's own: one on their machine, or
  their own key for a hosted one. The project never runs or proxies one
  (M13).
- **D21 Embedded recipe data.** Reading a page's schema.org data is a
  nice-to-have for the end, or for after the release (M16). The selection
  is the way in.

## Milestones

One PR each, in this order: server preparation (M1 to M4), two set-up PRs
for the extension (M5, M6), a clipper that can be used (M7), then one
addition at a time. From M8 on the order can change as things start to be
missed. Server PRs follow the server's rules in `AGENTS.md`. From M6 on, an
extension PR is done only after a pass by hand in a real Firefox:
anklipper's first such pass found three bugs its fakes had missed. The PR
that finishes a milestone marks it done here.

### M1 · server · Units become a shared vocabulary

**Done** (#154).

Today units are one global list that only staff add to: an unknown unit is
an error in the editor, and an import keeps it as text in `legacy_unit`.

- `Unit.owner`, blank for a global unit. Names are unique ignoring case
  within the global list and within each user's own, as for `Ingredient`.
- `find_unit` takes the owner and sees the global list plus their own, the
  global unit winning. A new `resolve_unit` makes a private unit on a miss,
  and the editor and the import use it.
- Size words and amount phrases (`small`, `to taste`) never become units:
  the editor keeps its error naming the field they belong in.
- A private unit has no dimension until staff make it global, by clearing
  its owner in admin. Aliases stay global.
- Update `units.md`, `shared-vocabularies.md` and the unit rule in
  `AGENTS.md`.

### M2 · server · Recipes get UUID keys

- `Recipe.id` becomes `UUIDField(primary_key=True, default=uuid.uuid7,
  editable=False)`. With it change the 41 routes that carry
  `<int:recipe_id>`, `delete_recipe --id` and the API reply's `id`. Steps,
  groups and rows keep their numbers.
- **The migration Django writes is not enough.** It copies each id as its
  decimal text, applies without complaint, and then no recipe loads. The
  same migration needs one more step, run on `recipes_recipe.id` and on
  `recipe_id` in `recipes_step`, `recipes_ingredientgroup` and
  `recipes_tag_recipe`:

  ```sql
  UPDATE <table> SET <column> = printf('%032x', CAST(<column> AS INTEGER))
  WHERE length(<column>) < 32;
  ```

- Recipe 10 becomes `00000000-0000-0000-0000-00000000000a`, and new ids are
  version 7, so ordering by id is still ordering by age, which the export,
  search and the trash rely on.
- It needs a reverse step: two older migration tests travel back through it
  with rows in place.
- Old numbered addresses (`/recipes/10/`) stop working. The rule is fixed,
  so a redirect is easy if bookmarks matter.
- **Done when** a migration test shows that a database with steps, groups,
  tags and a trashed recipe exports the same before and after; `make e2e`
  passes; and, after `make backup`, a copy of the real database has been
  migrated and its export compared. Only then the real one.

### M3 · server · A save can name its recipe's id

- `POST /recipes/api/recipes/?id=<uuid>`, for a body that holds one recipe,
  creates the recipe under that id.
- If the key's user already has a recipe with that id, live or in the
  trash, nothing is written and the reply is that recipe. Someone else's id
  is refused, without saying whose.

### M4 · server · The lists the clipper loads

- `GET /recipes/api/vocabulary/` answers with what the key's user can see,
  in named sections: `ingredients` and `units` (each entry the canonical
  name with every other spelling the server accepts for it: its plural, its
  aliases and their plurals), `cuisines` (dotted paths), `tags`, `limits`
  (the length each field of a save may have) and the user's name. The
  number of queries must not grow with the library.
- The extension only looks names up in these. It never inflects one itself,
  so the two cannot disagree about a plural.
- A later kind of data, such as nutrition, is a new section, not a new
  endpoint.
- One example of each request and reply of the API is kept as a JSON file
  with the server's tests, checked against what the views send. The
  extension's tests read the same files (M6).
- `AGENTS.md` and `import-export.md` say the app has one JSON endpoint:
  update both.

### M5 · extension · Set-up: the project and its quality gates

No feature: an extension that builds, loads in Firefox with an empty
sidebar, and cannot be merged red.

- Anklipper's toolchain files at their pinned versions: `package.json`,
  `wxt.config.ts`, `vitest.config.ts`, `tsconfig.json`, `eslint.config.js`,
  `.nvmrc`.
- The gates: Prettier, ESLint (with anklipper's rule that keeps browser APIs
  and Svelte out of the domain code), `svelte-check` and `tsc`, Vitest, and
  a build for Firefox and for Chrome. `make ext-qa` runs them all;
  `ext-install`, `ext-dev`, `ext-test` and `ext-build` sit beside it.
  `make qa` stays free of Node.
- The same gates as pre-commit hooks for files under `extension/`, and
  anklipper's TDD hook for agents (`.claude/hooks/check-tdd.sh`: no source
  module without a test), scoped to `extension/`.
- `.github/workflows/extension.yml`, run for changes to `extension/**`, its
  own file, the `Makefile`, the hook config and M4's JSON files.
- **Required checks.** A workflow skipped by its path filter never reports.
  So if `main` requires the server's `qa`, a PR that touches only
  `extension/` waits for it for ever (#145). If it does, move the path test
  from the workflows' triggers to a condition on their jobs: a job skipped
  by its own condition counts as passed.
- The server's tests police this PR: `tests/test_workflows.py` (every
  workflow's actions pinned to a commit, a timeout on every job, a read-only
  token; its ban on pnpm is narrowed to the server's workflows),
  `tests/test_makefile.py` (every target listed), `tests/test_dependabot.py`
  (an `npm` entry for `/extension` once `package.json` exists) and
  `tests/test_documentation.py` (no `pnpm install` in the developer guide's
  first-time setup).
- How to run it goes in `extension/README.md`, and an `extension/` section
  in `AGENTS.md` covers boundaries, permissions, privacy and TDD.
- **Done when** `make ext-qa` is green locally and in CI, a deliberate
  failure turns CI red, and a PR that touches only `extension/` can merge.

### M6 · extension · Set-up: the shell

Anklipper's plumbing with its tests, without its Anki half. Selected text
reaches the sidebar and the lists load; nothing is a recipe yet.

- Copied and adapted: `platform/`, the typed messages, the capture chain
  (menu or shortcut, read the selection with a line per list item or
  paragraph, store it, open the sidebar), the settings store and options
  page, and the manifest test that pins the permissions (D14). Folders as
  in anklipper's `src/`, with `nutrisho/` for the server's client where
  `anki/` was.
- New: the toolbar button, which opens the sidebar and clips the selection
  if there is one. `NutrishoClient` (port, `fetch` adapter, fake) with the
  lists call, its tests reading M4's JSON files. The options page takes the
  server's address (`make dev`'s `http://localhost:8987` to start with) and
  the API key, and asks for the host permission when saved. The sidebar
  shows the captured text, and either whose lists it loaded or what went
  wrong.
- The host permission is asked for without the port: MDN says Firefox's
  match patterns take none, so anklipper's `hostPermissionFor`, which keeps
  it, changes. Confirm it in the pass by hand.
- Drop anklipper's Chrome `key`, which exists for AnkiConnect's allowlist.
  Keep the pinned gecko id.
- **Done when**, in a real Firefox, text selected on a page shows in the
  sidebar by menu, shortcut and button, and the lists load from the dev
  server with a key from
  `make manage ARGS="create_api_token <username> --name clipper"`.

### M7 · extension · A clipper that can be used

- `RecipeDraft`, pure and written test-first: the id (a version 7 UUID,
  made when the draft starts), the name (from the page's title), the source
  (the page's address), blurb, servings, ingredient rows and steps, with
  *Add to* and *Replace* for name, blurb, ingredients and steps.
- **Scanning a line.** Each line sent to the ingredients becomes a row. The
  scan fills a field only when it is sure, and leaves every other word, in
  order, in *rest*:
  - the ingredient is the longest name from the loaded list that the line
    holds, stored in its canonical spelling;
  - the unit is a name from the loaded list directly before the ingredient;
  - the quantity is a number directly before the unit, or before the
    ingredient when there is no unit.

  | Line | Quantity | Unit | Ingredient | Rest |
  |------|----------|------|------------|------|
  | `Juice of 1 lemon` | 1 | | lemon | Juice of |
  | `1 (14-ounce) can diced tomatoes` | | | diced tomato | 1 (14-ounce) can |
  | `A fresh basket of boletus` | | | | A fresh basket of boletus |

  These are its first tests, with `lemon` and `diced tomato` in the list
  and `boletus` not. Lines it gets wrong join them as they turn up.
- Every field of a row can be edited. An ingredient or unit that is not in
  the lists is marked *new*, and the save makes it the user's own. A row
  with no ingredient stops the save. What is left in *rest* is saved in the
  row's note.
- Steps: one for each line or paragraph of the text, each editable.
- Drafts are kept in the extension's storage, so one survives the sidebar
  closing. A capture from another page starts a new draft, and the earlier
  ones stay listed until they are saved or discarded.
- *Save* posts the draft as a Nutrisho document to
  `POST /recipes/api/recipes/?id=<draft id>`, then shows *Open in Nutrisho*
  (`/recipes/<id>/?edit=1`) with the server's warnings, or the server's
  refusal as it came.
- **Done when** a recipe clipped from a real page opens on the dev server
  with its rows as the sidebar showed them, and saving it twice makes one
  recipe.

### M8 · extension · Names from the lists

- Typing in an ingredient, substitute or unit field offers the names in the
  loaded lists.
- A cuisine field that only picks from the tree, as on the site (anklipper's
  `Picker`).
- A tags field, comma-separated as on the site, with a tag that is not in
  the list marked *new*.
- The lists load again after a save, so the names it made are known.

### M9 · extension · Structure, as on the site

- A line among the ingredients can be made a group name (D7). The scan
  proposes it for a line that ends in a colon and holds nothing it knows
  (`For the sauce:`).
- Step titles. Rows and steps can be reordered and deleted, and a row moved
  to another group.
- Text too long for its field is flagged at the field before the save, from
  the `limits` loaded with the lists (D12).

### M10 · server · Harden the API (#149)

The parts the clipper meets: an expired key answered with
`code: token_expired`, 415 for a wrong content type, 429 with `Retry-After`,
and caps on the recipes and on the new names one request may bring. The cap
on new names is set from real clips, so an honest one fits.

### M11 · extension · Failures said properly

Until here the sidebar shows a failure as the server worded it. Now each
cause that needs a different fix has its own line: not set up, no host
permission, server unreachable, not a Nutrisho server, key missing or
refused, key expired, save refused (with the server's message and the field
it names), too large, too many requests, server error, malformed reply,
timeout. Every reply is checked for shape before it is used.

### M12 · extension · The look

The site's recipe page on a phone (`server/docs/features/design.md`), with a
clipboard on top.

- The tokens and the two text faces (Libre Caslon Text, IM Fell English SC)
  are copied into `extension/`. A test keeps the copies identical to the
  server's, and the extension workflow also runs when the server's change.
- No boxes: space and type separate things. *New* in `--marmalade`, *Save*
  on `--sunflower-wash`, errors in `--smock-red` and nothing else red, the
  lineout plate when nothing is clipped.
- Every control is labelled and reachable by keyboard, and changes are
  announced.
- A preview harness (anklipper's `preview/`) renders each state of the
  sidebar without a browser.

### M13 · extension · A model of the user's own

A second line scanner behind the same rows (D20); the loaded lists still say
which names are known. It starts with a design note: what is sent and to
whom, how the user turns it on, where its key lives (as D11), whether a
provider or a local model accepts a request from an extension's origin, and
what happens when the answer is not the shape asked for.

### M14 · server · API keys on the Config page (#150)

Users make a key (shown once), see their keys by name and last use, and
revoke one.

### M15 · extension · Release

- `ext-v<version>` tags and `extension/CHANGELOG.md`, by commitizen with a
  config of its own in `extension/` that counts only commits scoped `ext`,
  and the mirror filter on the server's side. Its default plugin has no
  scope filter: tried, it put the server's commits in the extension's
  changelog, and a `feat(ext)` commit raised the server's version. If that
  cannot be made to work, release-please for the extension only.
- Icons, and AMO's data-collection declaration: page content goes to a
  server, so anklipper's `none` does not apply.
- The file is signed by AMO and attached to the GitHub release, with an
  `update_url` so installs update. The signing job follows the tagging job
  in one workflow, since a tag made by CI starts no workflow of its own,
  and runs in the `store-publishing` environment with a required reviewer
  (#145).
- The production server's address joins the optional host permissions when
  there is one (#87).

### M16 · extension · Fill from the page

A nice-to-have, which can wait until after the release (D21). The capture
gesture with nothing selected reads the page's schema.org `Recipe` wherever
the page put it (alone, in a list, in `@graph`, under `mainEntity`, as
`utils/json_ld.py` does), keeps only what the draft uses, and fills the
draft's empty parts. Its ingredient lines go through the same scan. Real
pages' data is loose, so its fixtures are the shapes real pages use.

## Open questions

- Should users add their own cuisines too? Today the tree is staff-only;
  ingredients, tags and (after M1) units are not.
- What is left in *rest* at a save: into the note (assumed in M7), or must
  it be emptied first?
- Do the loaded lists need to refresh while the sidebar stays open, or is
  loading on open enough?
- The toolbar button opens the sidebar and clips the selection: assumed in
  M6, not confirmed.
- Should an export carry recipe ids, so that importing a file twice changes
  nothing?
- Listed or unlisted on the stores? Not needed before M15.

## Out of scope

- Images, nutrition, ratings and reviews from the page.
- Tags from a page's keywords.
- Microdata, and several recipes from one page.
- Changing a recipe after it is saved: that is the site's job.
- An offline queue of failed saves.
- Chrome as a release target, and any store listing for it, before the first
  Firefox release.
- Safari and Firefox for Android.

## Discarded

- htmx in the extension: its work is in the browser, not on a server.
- GraphQL: a handful of calls, and no other client.
- Checking names on the server (a preview call, a save that refuses new
  names): the lists loaded on open do it.
- An idempotency key for saves: UUID keys do it.
- Leaving all editing to the site after the save.
- A rough clipper before the quality gates.
- A `whoami` call: loading the lists is the connection test.
- Recipe data embedded in pages as the main way in.
- A model run or proxied by the project.
