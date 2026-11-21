# Nutrisho clipper

A browser extension that clips recipes from web pages into Nutrisho. You
select text on a recipe page, send it to the recipe's title, blurb,
ingredients or steps, check what it made of each ingredient line, and save.
Cuisines, tags and the look come in later milestones of
[plan 012](../docs/plans/012-recipe-clipper.md).

## Running it

You need Node and pnpm at the versions in [`.nvmrc`](.nvmrc) and
`packageManager` in [`package.json`](package.json). With
[corepack](https://nodejs.org/api/corepack.html), `corepack enable` gives you
the right pnpm. Run everything from the repository root:

```bash
make ext-install              # dependencies, from pnpm-lock.yaml
make ext-dev                  # Firefox, in a fresh profile, reloading on change
make ext-dev BROWSER=chrome   # the same in Chrome
make ext-test                 # the tests; ARGS="src/sidebar" narrows them
make ext-qa                   # every check CI runs
make ext-build                # .output/firefox-mv3/ and .output/chrome-mv3/
```

The other `ext-` targets run `make ext-install` first when `node_modules` is
missing or older than `pnpm-lock.yaml` or `package.json`, so a fresh checkout
or a pull that changed the dependencies needs no separate step.

`make ext-dev` opens the browser for you, through
[web-ext](https://github.com/mozilla/web-ext), in a profile of its own kept
in `.wxt/firefox-data/`, so the settings you save there survive a restart. To load a build into your own
Firefox, open `about:debugging`, choose *This Firefox*, then *Load Temporary
Add-on*, and pick `.output/firefox-mv3/manifest.json`. Open the sidebar from
the *View* menu, under *Sidebar*.

## Using it

1. Start the server (`make dev`, on `http://localhost:8987`) and make an API
   key for your user. It is shown once:

   ```bash
   make manage ARGS="create_api_token <username> --name clipper"
   ```

2. Open the clipper's settings (from the sidebar, or the add-on's
   *Preferences* in `about:addons`), enter the server's address and the key,
   and save. The browser asks once for permission to reach that address. Only
   `localhost` and `127.0.0.1` are allowed for now.
3. Select text on a page, right-click, and choose where it goes under *Clip
   into Nutrisho*: *Title* (replaces the recipe's name), *Blurb*,
   *Ingredient group*, *Steps* (each adds to what is there) or *Clipboard*.
   The sidebar opens with a new recipe named after the page, and the text is
   also in the clipboard at the bottom. <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>N</kbd>
   and the toolbar button clip to the clipboard only.
4. Each ingredient line becomes a row: the ingredient is the longest name
   from your lists in the line, the unit a name from your lists just before
   it (`600ml` counts), and the quantity a number just before that, or else
   the nearest number before it (`2 large eggs`). An amount
   with its unit can also stand a few words earlier: in `190g plain flour`,
   *plain* stays in *Rest*. A line with no name from your lists still keeps
   the amount and unit it starts with (`90ml dark maple syrup`). Every other word stays in *Rest*, commas
   included, which is saved in the row's note. A line that starts with a
   comma (`, cubed`) belongs to the line before. A name your
   lists do not have is marked *new*, and saving makes it one of your own.
   When nothing in a group's first line is known, it becomes the group's name
   (`For the sauce:`).
5. From the clipboard, send all of it, or the part you select, to any part
   of the recipe with *Add* or *Replace*. You can also type or paste into it.
6. *Save* sends the recipe to your Nutrisho and offers *Open in Nutrisho*.
   Saving the same recipe again changes nothing.

Recipes not yet saved stay in the sidebar after it closes, until the browser
is restarted: a new browser session starts empty. Clipping from another page
starts another recipe; pick between them under *Draft*, *Discard this draft*
to drop one, or *Clear all* at the top to start again.

The key is kept in the browser's local storage, never synced, and the
settings page never shows it again. Only the server's address you saved is
ever contacted, and only the recipe you save is sent to it.

## Checks

`make ext-qa` runs Prettier, ESLint, `svelte-check` and `tsc`, Vitest, and a
build for each browser. The same command runs in the git hooks, on any commit
that touches this directory, and in CI
([`extension.yml`](../.github/workflows/extension.yml)). `make qa`, the
server's gate, never needs Node.

Vitest runs two projects: plain TypeScript tests in Node, and component tests
(`*.svelte.test.ts`, `*.dom.test.ts`) in jsdom. The tests in
`tests/manifest/` build the extension for each browser and read the manifest
that comes out.

## Layout

```
src/
  core/                    # pure TypeScript: capture, clipping, settings, the lists, the ports and their fakes
  manifest/                # permissions, ids and the shortcut, merged into the manifest
  messaging/               # the typed messages between background and content script
  nutrisho/                # the server's client: a `fetch` adapter for the NutrishoClient port
  platform/                # the only code that touches `browser.*`, each with a fake
  background/              # the capture chain: gesture, read the page, store, open the sidebar
  content/                 # reads the selection off the page; injected on a gesture only
  sidebar/                 # the sidebar's Svelte components
  options/                 # the settings form
  entrypoints/             # background, content script, sidebar and options pages: they only wire
tests/
  manifest/                # the built manifest, per browser
  setup/                   # Vitest setup: fake browser APIs, Testing Library
  support/                 # reads the server's API examples
wxt.config.ts              # WXT: source directory, Svelte, manifest fields
vitest.config.ts           # the two test projects
eslint.config.js           # includes the rule that keeps browser APIs and Svelte out of domain code
```

The rules for the code (boundaries, permissions, privacy, tests first) are in
the Extension section of [`AGENTS.md`](../AGENTS.md#extension).

## How it fits with the server

- The clipper talks to two endpoints, `POST /recipes/api/recipes/` and
  `GET /recipes/api/vocabulary/`, with `Authorization: Bearer <key>`, from its
  own pages and never from a content script. One example of each request and
  reply is in [`server/tests/api_examples/`](../server/tests/api_examples/);
  the server's tests check them against its views, and the extension's tests
  read the same files.
- Commits that touch only the extension are scoped `ext` (`feat(ext): ...`).
- Releases will be tagged `ext-v<version>`, separate from the server's
  `server-v<version>`. The release workflow will build the extension, have
  Mozilla sign it and attach the signed file to the GitHub release. Whether it
  is listed on a store is an open question in the plan.
