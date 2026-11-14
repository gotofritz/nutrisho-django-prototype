# Nutrisho clipper

A browser extension that clips recipes from web pages into Nutrisho. It is not
written yet: this directory holds its place in the repository (#145).

## Plan

- **Tooling**: Node with [web-ext](https://github.com/mozilla/web-ext), its own
  `package.json` and lockfile here, independent of the server's uv project.
- **Make targets**: in the top-level `Makefile`, prefixed `ext-` (`ext-lint`,
  `ext-test`, `ext-build`), so the server's plain `make test` and `make qa`
  stay as they are.
- **CI**: `.github/workflows/extension.yml`, run only for changes under
  `extension/**` and its own workflow file. The server workflows already skip
  extension-only changes.
- **Dependabot**: an `npm` entry for `/extension`, added with the first
  `package.json`.
- **Releases**: tagged `ext-v<version>`, with a changelog here. Server releases
  are tagged `server-v<version>`, and the server's commitizen config ignores
  `ext-v*` tags. Scope extension commits `ext`, e.g. `feat(ext): ...`.
- **Publishing**: a workflow triggered by an `ext-v*` tag builds the extension
  and submits it to Mozilla AMO and the Chrome Web Store. Its publishing job
  runs in a `store-publishing` GitHub environment with a required reviewer,
  which holds the store credentials as environment secrets.
