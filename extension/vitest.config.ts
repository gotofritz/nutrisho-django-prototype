import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vitest/config";
import { WxtVitest } from "wxt/testing/vitest-plugin";

// Two projects, as in anklipper. Domain logic runs in `node`, so anything
// reaching for the DOM fails loudly; Svelte components run in `jsdom`. A test
// opts into jsdom by its filename: `*.svelte.test.ts` or `*.dom.test.ts`.
const DOM_TESTS = ["**/*.svelte.test.ts", "**/*.dom.test.ts"];
const ALL_TESTS = ["src/**/*.test.ts", "tests/**/*.test.ts"];

export default defineConfig({
  plugins: [WxtVitest()],
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "node",
          environment: "node",
          include: ALL_TESTS,
          exclude: DOM_TESTS,
          setupFiles: ["./tests/setup/fake-browser.setup.ts"],
        },
      },
      {
        // Svelte only compiles here; the node project stays free of it, so a
        // domain module that imports a component fails rather than passing.
        extends: true,
        plugins: [svelte(), svelteTesting()],
        test: {
          name: "jsdom",
          environment: "jsdom",
          include: DOM_TESTS,
          setupFiles: [
            "./tests/setup/fake-browser.setup.ts",
            "./tests/setup/testing-library.setup.ts",
          ],
        },
      },
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,svelte}"],
      exclude: ["src/entrypoints/**", "**/*.test.ts"],
    },
  },
});
