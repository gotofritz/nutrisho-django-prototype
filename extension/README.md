# Nutrisho clipper

A browser extension that will clip recipes from web pages into Nutrisho. It
does nothing useful yet: today it builds, loads in Firefox or Chrome, and opens
an empty sidebar. Recipes come in later milestones of
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

`make ext-dev` opens the browser for you. To load a build into your own
Firefox, open `about:debugging`, choose *This Firefox*, then *Load Temporary
Add-on*, and pick `.output/firefox-mv3/manifest.json`. Open the sidebar from
the *View* menu, under *Sidebar*.

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
  entrypoints/sidepanel/   # the sidebar page: mounts the app, nothing else
  sidebar/                 # the sidebar's Svelte components
tests/
  manifest/                # the built manifest, per browser
  setup/                   # Vitest setup: fake browser APIs, Testing Library
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
  will read the same files.
- Commits that touch only the extension are scoped `ext` (`feat(ext): ...`).
- Releases will be tagged `ext-v<version>`, separate from the server's
  `server-v<version>`. The release workflow will build the extension, have
  Mozilla sign it and attach the signed file to the GitHub release. Whether it
  is listed on a store is an open question in the plan.
