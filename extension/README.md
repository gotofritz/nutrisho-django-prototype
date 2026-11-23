# Nutrisho clipper

A browser extension that clips recipes from web pages into Nutrisho. You
select text on a recipe page, send it to the recipe's title, blurb,
ingredients or steps, check what it made of each ingredient line, give it a
cuisine and tags, and save. It was built under
[plan 012](../docs/archive/2026-11-23-0008-a009848-012-recipe-clipper.md).

## Installing it

The clipper is not listed on Firefox's add-on site while the server is not
yet public. Each release on GitHub, tagged `ext-v` and a version, carries a
copy signed by Mozilla:

1. Open the newest `ext-v` release on the
   [releases page](https://github.com/gotofritz/nutrisho-django-prototype/releases)
   in Firefox, and click its `.xpi` file
2. Allow the install when Firefox asks, then open the clipper from the
   toolbar button, or the *View* menu under *Sidebar*

Firefox then looks for newer versions by itself and updates the clipper as
it does any other add-on. On its first save the clipper asks where your
Nutrisho is: see *Using it* below.

When you save, the recipe you clipped, with the text you picked from the
page and the page's address, goes to your own Nutrisho. When you ask a model,
a group's lines or the steps go to the model you set up. Firefox lists both
as data the clipper sends, when it is installed.

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
make ext-zip                  # zips of each build, and of the sources for Mozilla
make ext-preview              # each state of the sidebar and settings, in a plain page
make ext-release              # a release branch: the next version and its changelog
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

1. Start the server (`make dev`, on `http://127.0.0.1:8987`), sign in, and
   make an API key on *Config*, then *API keys*. It is shown once, so copy it
   then. (`make manage ARGS="create_api_token <username> --name clipper"`
   makes one from the command line.)

2. Open the clipper's settings (from the sidebar, or the add-on's
   *Preferences* in `about:addons`), enter the server's address and the key,
   and save. The browser asks once for permission to reach that address.
   The clipper talks to a Nutrisho on this computer (`127.0.0.1` or
   `localhost`, over `http`) or at `https://nutrisho.com`. *Advanced Mode*,
   folded away at the bottom of the sidebar, switches between the two and
   sets the port: pick one and press *Use this server*.
3. Select text on a page, right-click, and choose where it goes under *Clip
   into Nutrisho*: *Title* (replaces the recipe's name), *Blurb*,
   *Ingredient group* (a new group), *Ingredient* (adds to the open group, or
   starts one when none is open) or *Steps* (each adds to what is there).
   The sidebar opens with a new recipe named after the page.
   <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>N</kbd> and the toolbar button clip
   to a new ingredient group.
4. Each ingredient line becomes a row. The ingredient is the longest name
   from your lists in the line. The unit is a name from your lists just
   before it (`600ml` counts) or, failing that, just after it
   (`2 garlic cloves`). The quantity is the number just before the unit, or
   else the nearest number before the ingredient (`2 large eggs`). An amount
   with its unit can also stand a few words earlier: in `190g plain flour`,
   *plain* stays in *Rest*. A line with no name from your lists still keeps
   the amount and unit it starts with (`90ml dark maple syrup`). Every other
   word stays in *Rest*, commas included. *Rest* is a scratch pad and is
   not saved: move what you want into a field such as *Note*, and clear the
   rest with 🗑.
   A line belongs to the one before when it starts with a comma or a bracket
   (`(about 2 tsp)`), or the line before ends with a comma. A name your
   lists do not have is marked *new*, and saving makes it one of your own.
   A group's first line becomes its name when it has no amount and either
   nothing in it is known or it starts with *For* (`For the sauce:`). One
   group is open at a time: ▼ opens another and ▲ closes it. Each row
   shows as one line, the way a printed recipe reads it; click the line to
   edit the row, and ▲ folds it again. One row is open at a time, on a pale
   yellow background, and a row with something to fix opens by itself.
   Each group and the open row have × to delete them. ↑ and ↓ move a row;
   the first or last row of a group moves on into the group before or
   after, which opens. ¶ turns a row that is really a heading (`To serve`)
   into the name of a new group holding the rows below it. *+ ingredient*
   at the end of a group adds a row, and *+ group* below the groups adds a
   group; a row left empty is not saved. Each step has a title as well as
   its text, and shows as one line too until you click it; *+ step* adds
   one, and on the open step ↑ and ↓ move it and × deletes it. An empty
   step is left out when you save. Under the recipe's name, the servings,
   cuisine, tags and source show as one line with the blurb beneath; click
   them to edit. Only one thing is open at a time, so opening a step folds
   the row you had open. Text too long for its field is marked at the field as
   you type, says by how much, and stops a save.
5. *Advanced Mode*, at the bottom, picks the server and its port, and keeps
   a *Log* of each request to your Nutrisho and its reply, with sizes and
   times but never your key or what was sent. Only a problem with your lists
   shows outside it.
6. As you type an ingredient, substitute or unit, the field offers the
   names in your lists. *Cuisine* offers the paths in the cuisine tree, such
   as `med.italy.sicily`; a bare name that only one place has, such as
   `sicily`, works too. *Tags* are separated by commas, as on the site. A
   cuisine or tag your lists do not have is marked *new*, and saving makes it
   one of your own: `med.italy.marche` goes inside `med.italy`, and a name
   with no dots is a new area.
7. *Clip* sends the recipe to your Nutrisho and offers *Open in Nutrisho*.
   Saving the same recipe again changes nothing. Your lists load again after
   a save, so the names it made are no longer marked *new*.
8. With a model of your own set up under *Your models* in *Advanced Mode*,
   each group has *Ask the model*: its lines, and nothing else, go to the
   model, and the rows it answers replace the group's. A row whose fields
   are not in its line keeps its own scan, a line in another language comes
   back in English, and *Undo the model's rows* puts the group back. *Ask the
   model* by *Steps* rewrites the method short and colloquial, a stage of the
   cooking to a step; *Undo the model's steps* puts it back. The model can be MLX or llama.cpp on your computer, as
   [timbuktu](https://github.com/gotofritz/timbuktu/blob/main/docs/user-guide.md#choosing-an-ai-backend)
   starts them, or Anthropic with your own key, in a workspace of its own
   with a low spend limit (see below). You can keep several, each under a
   name: *+ add model* adds one, ✎ edits one and × deletes it, and *Default
   model* picks the one *Ask the model* uses, or *Built in* for none. To ask
   another just once, hold *Ask the model* for 2 seconds, right-click it, or
   press Shift+Enter on it, and pick one from the menu; the next click asks
   the default again. The note after an ask names the model that answered. *Advanced Mode* says
   whether your model answers, and *Check the model* asks again.

Recipes not yet saved are kept in your browser, even after a restart. A new
browser session opens none of them: pick one under *Draft*, or clip from its
page again. Clipping from another page starts another recipe, while clips
from the same page go on into its recipe even after you change *Source*; ↗
next to *Source* opens it in a new tab. Pick between recipes under *Draft*,
*Discard this draft* to drop one, or *Clear all* at the top to start again.

The keys, Nutrisho's and a model's, are kept in the browser's local storage,
never synced, and are never shown again. Only the
addresses you saved are ever contacted: the recipe goes to your Nutrisho when
you save, and a group's lines, or the steps, to your model when you ask it.

### Capping what Anthropic can spend

Anthropic sets spend limits on a workspace, not on a key, so give the clipper
a workspace of its own:

1. In the [Anthropic Console](https://console.anthropic.com), open
   *Settings*, then *Workspaces*, and create one, for example *Clipper*
2. Open it and set its spend limit to a small monthly amount
3. Under *API keys*, create the key in that workspace, and paste it into the
   set-up's *Anthropic key*

When the workspace reaches its limit, the model stops answering until the
next month, and nothing else of yours is touched. Deleting the key, or the
workspace, cuts the clipper off alone. The organisation's own limit, under
*Settings*, then *Limits*, still caps everything together.

`make ext-preview` serves [`preview/`](preview/) on Vite's address: a picker of
scenes (nothing clipped, a key expired, a draft filled in, saved, the
settings), each mounted on the in-memory fakes at a sidebar's width. Use it to
look at a change of style without loading the extension.

## The look

The clipper looks like the site (`server/docs/features/design.md`):
`src/styles/tokens.css` holds the site's colour tokens and its two text faces,
`public/fonts/` and `public/img/` the font files and the lineout plate, all
copies of the server's; `tests/look/site-copies.test.ts` fails when either
side changes without the other, and a change to those server files runs the
extension's checks too. `src/styles/clipper.css` styles the elements as the
site does: no boxes, a field is a line, actions are small capitals, Clip sits
on a sunflower wash, and errors alone are smock red. Components add layout
only.

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
  models/                  # the user's own model: MLX and llama.cpp (OpenAI-compatible) and Anthropic
  platform/                # the only code that touches `browser.*`, each with a fake
  background/              # the capture chain: gesture, read the page, store, open the sidebar
  content/                 # reads the selection off the page; injected on a gesture only
  sidebar/                 # the sidebar's Svelte components
  options/                 # the settings form
  entrypoints/             # background, content script, sidebar and options pages: they only wire
  styles/                  # the site's tokens and faces, and the clipper's element rules
public/                    # copies of the site's fonts and lineout plate
preview/                   # the look preview: each state, on the fakes
tests/
  look/                    # the copies match the site's; every preview scene mounts
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
  Only those count towards its releases, and the server's leave them out.
- Releases are tagged `ext-v<version>`, separate from the server's
  `server-v<version>`, and its version is the one in `package.json`.
  `make ext-release` starts one: see
  [the developer guide](../docs/developer-guide.md#the-extensions-releases).
  When its PR merges, CI tags it, attaches the zips to the GitHub release,
  and has Mozilla sign the Firefox build as an unlisted add-on, whose `.xpi`
  it attaches too. The manifest's `update_url` reads `updates.json` on the
  `ext-updates` branch, which the signing job rewrites to name that `.xpi`.
- The icon is drawn once, in [`public/icon/icon.svg`](public/icon/icon.svg),
  after the site's favicon, and rendered as a PNG at each size in
  `public/icon/`, which WXT puts in the manifest.
