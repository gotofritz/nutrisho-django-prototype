import { defineConfig } from "wxt";

// Firefox is the first target (plan 012, D18); `pnpm build:chrome` keeps the
// Chrome build compiling from the start. The permissions, the pinned gecko id
// and the manifest test that holds them arrive with the shell (M6).
export default defineConfig({
  srcDir: "src",
  modules: ["@wxt-dev/module-svelte"],
  // Firefox still accepts MV2, and WXT defaults to it there. Pin MV3 so both
  // targets build the same manifest generation.
  manifestVersion: 3,
  manifest: {
    // `package.json`'s name is the npm one; the description is read from it.
    name: "Nutrisho clipper",
  },
});
