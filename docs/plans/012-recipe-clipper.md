# Plan 012: The recipe clipper extension

## Status: In progress, M1 to M7 done (#154, #156, #158, #160, #162, #166, #168)

## What we are building

A browser extension, in `extension/` (#145), that clips a recipe from the
page the user is reading into their Nutrisho.

1. The user selects text on a recipe page and clips it from the right-click
   menu, choosing where it goes: the title, the blurb, an ingredient group,
   the steps, or only the clipboard. A shortcut and the toolbar button clip to
   the clipboard.
2. A sidebar opens with the recipe so far. Clipped text also lands in a
   clipboard at the bottom, from where it can be added to any part of the
   recipe, or replace it.
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
- **D3 Where text goes.** The right-click menu's submenu (*Title*, *Blurb*,
  *Ingredient group*, *Steps*, *Clipboard*) sends a capture to that part of
  the recipe and to the clipboard: the title replaces the name, the others
  add to what is there. The shortcut and the toolbar button send it to the
  clipboard only. From the clipboard, at the bottom of the sidebar, text is
  added to a part of the recipe or replaces it; typed or pasted text is
  treated the same. (Changed after a first use of M7: the clipboard alone was
  one step too many.)
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
- **D7 Group headings.** Ingredients come in groups, one per capture sent to
  *Ingredient group*. A first line that holds nothing the lists know, with
  more lines after it, is taken for the group's name (`For the sauce:`), and
  every name can be edited (M7).
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

### ✅ M1 · server · Units become a shared vocabulary

Done (#154). Units are global (staff-curated) plus each user's own;
`resolve_unit` makes a private unit on a miss, and size words and amount
phrases never become units.

### ✅ M2 · server · Recipes get UUID keys

Done (#156). `Recipe.id` is a version 7 UUID and the recipe routes take
`<uuid:recipe_id>`; migration 0033 rewrites the old ids as hex (recipe 10
becomes `...00000000000a`) and numbers them again going back. Old numbered
addresses are gone. Still to do by hand before deploying: `make backup`,
migrate a copy of the real database, compare its export, then the real one.

### ✅ M3 · server · A save can name its recipe's id

Done (#158). `POST /recipes/api/recipes/?id=<uuid>` (a version 7 UUID, one
recipe per body) creates the recipe under that id. The same id again writes
nothing and answers 200 with the recipe, live or trashed; another user's id
is a 409 that names nobody.

### ✅ M4 · server · The lists the clipper loads

Done (#160). `GET /recipes/api/vocabulary/` answers with the key's user's
`ingredients` and `units` (each with every spelling the server accepts),
`cuisines`, `tags`, `limits` and name, in a fixed number of queries. One
example of each API request and reply lives in `server/tests/api_examples/`,
checked against the views; the extension's tests read the same files.

### ✅ M5 · extension · Set-up: the project and its quality gates

Done (#162). `extension/` is a WXT, Svelte 5 and TypeScript project at
anklipper's pinned versions; it builds for Firefox and Chrome and opens an
empty sidebar. `make ext-qa` (Prettier, ESLint with the ports rule,
`svelte-check` and `tsc`, Vitest, both builds) runs in the git hooks and in
`extension.yml`, and anklipper's TDD hook guards `extension/` for agents.
Every workflow now always runs, and a first `changes` job skips the checks a
change does not concern, so a required check never waits on an
extension-only PR.

### ✅ M6 · extension · Set-up: the shell

Done (#166). Anklipper's plumbing, without its Anki half: the context menu,
Alt+Shift+N and a new toolbar button read the selection (a line per list
item or paragraph), store it as a clipping and open the sidebar. The options
page takes the server's address (loopback only) and an API key, and asks for
the host permission, without a port, when saved. `NutrishoClient` loads the
lists, tested against M4's JSON files, and the sidebar shows the clipping and
whose lists loaded or what went wrong. No Chrome `key`; the gecko id is
pinned.

### ✅ M7 · extension · A clipper that can be used

Done (#168). A clipping starts a draft named after the page, with a version
7 UUID; a clipping from another page starts another. The right-click submenu
sends it to the title, blurb, a new ingredient group or the steps as well as
to the clipboard, which sits at the bottom and has *Add* and *Replace* for
each part (D3). Unsaved drafts and the clipping are kept in session storage,
so they survive the sidebar closing and a new browser session starts empty;
*Clear all* drops them. Each ingredient line is scanned against the lists
(longest ingredient, a unit just before it or an amount and unit a few words
earlier, a number just before that or else the nearest one before it, `600ml` read as `600 ml`, an amount and unit starting a line kept even when
the ingredient is unknown), the rest kept in
*rest* with its commas and saved in the note, and
unknown names marked *new*; a group's first line is its name when nothing
in it is known (D7); a group or a row folds to one line or is deleted, and a step
has a title. *Save* checks the name, servings, quantities and that every row has an
ingredient, posts the draft as a Nutrisho document, and shows *Open in
Nutrisho*, the server's warnings, or its refusal as it came. The draft and the
save are tested against the server's API examples.

### M8 · extension · Names from the lists

- Typing in an ingredient, substitute or unit field offers the names in the
  loaded lists.
- A cuisine field that only picks from the tree, as on the site (anklipper's
  `Picker`).
- A tags field, comma-separated as on the site, with a tag that is not in
  the list marked *new*.
- The lists load again after a save, so the names it made are known.

### M9 · extension · Structure, as on the site

- A line inside a group can be made a group name, splitting it (D7: M7
  already names a group from its first line).
- Rows and steps can be reordered, steps deleted, and a row moved to another
  group. (Step titles, and folding and deleting groups and rows, came early, in M7.)
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
