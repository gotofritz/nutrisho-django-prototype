import { expect, it } from "vitest";

// `make ext-dev` opens Firefox through web-ext, which WXT treats as an
// optional peer: without it WXT logs the miss only under --debug, builds, and
// opens nothing. Pinned as a dev dependency, and held here. The name goes
// through a variable because web-ext ships no types, and none are needed.
const WEB_EXT: string = "web-ext";

it("can load web-ext, which opens the browser for make ext-dev", async () => {
  await expect(import(WEB_EXT)).resolves.toBeDefined();
});
