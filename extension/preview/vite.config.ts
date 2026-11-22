import { svelte } from "@sveltejs/vite-plugin-svelte";
import { resolve } from "node:path";
import { defineConfig } from "vite";

const EXTENSION = resolve(import.meta.dirname, "..");

/**
 * The look preview (plan 012, M12; from anklipper): each state of the sidebar
 * and the settings, in a plain page, without a browser extension around it.
 *
 * Not a WXT build: every `browser.*` call sits behind a port, so the sidebar
 * mounts on the in-memory fakes with nothing shimmed. `public/` is the one
 * the extension is built from, so `/fonts/…` and `/img/…` resolve here as
 * they do in the packaged extension.
 */
export default defineConfig({
  root: import.meta.dirname,
  plugins: [svelte()],
  publicDir: resolve(EXTENSION, "public"),
  resolve: { alias: { "@": resolve(EXTENSION, "src") } },
  build: { outDir: resolve(EXTENSION, ".output/preview"), emptyOutDir: true },
});
