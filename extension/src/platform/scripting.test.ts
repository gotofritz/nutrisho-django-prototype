import { browser } from "wxt/browser";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CONTENT_SCRIPT_FILE, createScripting } from "./scripting";

beforeEach(() => {
  browser.scripting = { executeScript: vi.fn() } as never;
});

describe("scripting", () => {
  it("injects the built content script into the tab it was given", async () => {
    const result = await createScripting().inject(7);

    expect(result).toEqual({ ok: true, value: undefined });
    expect(browser.scripting.executeScript).toHaveBeenCalledWith({
      target: { tabId: 7 },
      files: [CONTENT_SCRIPT_FILE],
    });
  });

  // The PDF viewer, `about:` pages, and the add-on listing all refuse. Each is
  // ordinary, and the caller degrades rather than crashing.
  it("reports a page that refuses injection as its own kind", async () => {
    browser.scripting.executeScript = vi.fn(() => {
      throw new Error("Missing host permission for the tab");
    });

    const result = await createScripting().inject(7);

    expect(result.ok).toBe(false);
    expect(result.ok === false && result.error.kind).toBe("not-injectable");
  });

  it("reports a tab that has gone away as its own kind", async () => {
    browser.scripting.executeScript = vi.fn(() => {
      throw new Error("No tab with id: 7");
    });

    const result = await createScripting().inject(7);

    expect(result.ok === false && result.error.kind).toBe("no-tab");
  });

  it("keeps any other failure distinguishable from those two", async () => {
    browser.scripting.executeScript = vi.fn(() => {
      throw new Error("something else entirely");
    });

    const result = await createScripting().inject(7);

    expect(result.ok === false && result.error.kind).toBe("injection-failed");
  });
});
