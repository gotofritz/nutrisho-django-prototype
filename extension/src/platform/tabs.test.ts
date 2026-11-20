import { browser } from "wxt/browser";
import { beforeEach, describe, expect, it } from "vitest";

import { createTabs } from "./tabs";

// A browser always has a focused window; the fake starts without one.
beforeEach(async () => {
  await browser.windows.create({ focused: true });
});

describe("tabs", () => {
  it("reports the active tab of the current window", async () => {
    await browser.tabs.create({
      url: "https://example.com/article",
      active: true,
    });

    await expect(createTabs().activeTab()).resolves.toEqual({
      id: expect.any(Number),
      url: "https://example.com/article",
      title: undefined,
    });
  });

  // Nothing focused is ordinary — a devtools window, a browser starting up.
  it("reports no active tab as undefined rather than throwing", async () => {
    await expect(createTabs().activeTab()).resolves.toBeUndefined();
  });
});
