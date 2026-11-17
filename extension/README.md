# Nutrisho clipper

A browser extension that clips recipes from web pages into Nutrisho. It is not
written yet: this directory holds its place in the repository (#145).

## Plan

The design, the stack and the milestones are in
[`docs/plans/012-recipe-clipper.md`](../docs/plans/012-recipe-clipper.md). In
short: WXT, Svelte and TypeScript, as in
[anklipper](https://github.com/gotofritz/anklipper); a sidebar where text
selected on the page is clipped into a draft recipe, checked against the
library's ingredients, units and cuisines, edited as on the site and saved;
and, later, the storybook look. Server preparation comes first, then the
extension's quality gates, then a clipper that can be used, and everything
after it adds to one that works. What stays as below:

- **Server side**: the clipper saves through `POST /recipes/api/recipes/` with
  `Authorization: Bearer <key>`, from its own pages and never from a content
  script. The server already takes a schema.org Recipe or a Nutrisho document
  there (#78); see `server/docs/features/import-export.md`. The plan lists the
  endpoints still to add.
- **Tooling**: Node and pnpm with [WXT](https://wxt.dev) (which drives
  [web-ext](https://github.com/mozilla/web-ext)), its own `package.json` and
  lockfile here, independent of the server's uv project.
- **Make targets**: in the top-level `Makefile`, prefixed `ext-` (`ext-dev`,
  `ext-test`, `ext-qa`, `ext-build`), so the server's plain `make test` and
  `make qa` stay as they are.
- **CI**: `.github/workflows/extension.yml`, run for changes under
  `extension/**`, its own workflow file and the files its tests read. It
  comes with the extension's first pull request (the plan's M5). The server
  workflows already skip extension-only changes.
- **Dependabot**: an `npm` entry for `/extension`, added with the first
  `package.json`.
- **Releases**: tagged `ext-v<version>`, with a changelog here. Server releases
  are tagged `server-v<version>`, and the server's commitizen config ignores
  `ext-v*` tags. Scope extension commits `ext`, e.g. `feat(ext): ...`.
- **Publishing**: the release workflow builds the extension, has Mozilla sign
  it and attaches the signed file to the GitHub release. Whether it is listed
  on a store is an open question in the plan, and the Chrome Web Store waits
  for the first Firefox release. The publishing job runs in a
  `store-publishing` GitHub environment with a required reviewer, which holds
  the store credentials as environment secrets.
