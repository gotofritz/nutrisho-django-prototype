import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "wxt";

import { manifestExtras } from "./src/manifest/manifest";

// A profile kept between runs of `make ext-dev`, so the settings, the API key
// and the host permission granted to the clipper survive a restart (from
// anklipper).
const FIREFOX_PROFILE = resolve(".wxt/firefox-data");

// Firefox is the first target (plan 012, D18); `pnpm build:chrome` keeps the
// Chrome build compiling from the start.
export default defineConfig({
  srcDir: "src",
  modules: ["@wxt-dev/module-svelte"],
  // Firefox still accepts MV2, and WXT defaults to it there. Pin MV3 so both
  // targets build the same manifest generation.
  manifestVersion: 3,
  manifest: ({ browser }) => ({
    // `package.json`'s name is the npm one; the description is read from it.
    name: "Nutrisho clipper",
    // The permission ceiling, the gestures and the pinned id live in
    // `src/manifest/manifest.ts`, where a test pins them (D14). WXT adds the
    // sidebar itself, from the sidepanel entrypoint: `sidebar_action` on
    // Firefox, `side_panel` and its permission on Chrome.
    ...manifestExtras(browser),
  }),
  webExt: {
    firefoxProfile: FIREFOX_PROFILE,
    keepProfileChanges: true,
  },
  hooks: {
    // web-ext treats `firefoxProfile` as a directory only if it already
    // exists; otherwise it looks for a named profile and fails. WXT does not
    // pass --profile-create-if-missing, so create it here, on the last hook
    // before the runner opens the browser.
    "server:started"(wxt) {
      if (wxt.config.browser === "firefox") {
        mkdirSync(FIREFOX_PROFILE, { recursive: true });
      }
    },
  },
});
