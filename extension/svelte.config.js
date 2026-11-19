import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

// `lang="ts"` in components goes through Vite's TypeScript transform, so the
// build, the test runner, and svelte-check all agree.
export default { preprocess: vitePreprocess() };
