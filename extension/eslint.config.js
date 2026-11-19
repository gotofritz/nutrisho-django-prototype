import js from "@eslint/js";
import prettier from "eslint-config-prettier/flat";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";

import autoImports from "./.wxt/eslint-auto-imports.mjs";
import svelteConfig from "./svelte.config.js";

const PORTS_NOT_BROWSER =
  "The domain layer depends on ports, not on browser APIs. Inject an adapter.";
const NO_UI_FRAMEWORK =
  "The domain layer must not depend on the UI framework. Keep Svelte in components.";

export default ts.config(
  { ignores: [".output/", ".wxt/", "coverage/", "node_modules/"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs.recommended,
  {
    // `browser`, `defineBackground`, … are injected by WXT rather than
    // imported, so ESLint has to be told they exist.
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...autoImports.globals },
    },
  },
  {
    files: ["**/*.svelte", "**/*.svelte.ts"],
    languageOptions: {
      parserOptions: {
        parser: ts.parser,
        extraFileExtensions: [".svelte"],
        svelteConfig,
      },
    },
  },
  {
    // Ports and adapters (plan 012, D13): the draft and its rules are pure
    // TypeScript. `src/platform/` is the adapter layer and the only place
    // `browser.*` is reached; `src/nutrisho/` is an adapter too, whose outside
    // edge is `fetch`, with what it needs from the browser injected.
    files: [
      "src/core/**/*.ts",
      "src/manifest/**/*.ts",
      "src/messaging/**/*.ts",
      "src/nutrisho/**/*.ts",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            { name: "wxt/browser", message: PORTS_NOT_BROWSER },
            { name: "webextension-polyfill", message: PORTS_NOT_BROWSER },
            { name: "svelte", message: NO_UI_FRAMEWORK },
          ],
          patterns: [{ group: ["*.svelte"], message: NO_UI_FRAMEWORK }],
        },
      ],
    },
  },
  // Last: turns off every rule Prettier already decides.
  prettier,
);
