import { describe, expect, it, vi } from "vitest";

import { createOptionsPage } from "./options";

describe("createOptionsPage", () => {
  it("opens the browser's own options page for this extension", async () => {
    const openOptionsPage = vi.fn(async () => undefined);

    const result = await createOptionsPage({ openOptionsPage }).open();

    expect(openOptionsPage).toHaveBeenCalled();
    expect(result).toEqual({ ok: true, value: undefined });
  });

  it("reports a refusal rather than throwing into a click handler", async () => {
    const result = await createOptionsPage({
      openOptionsPage: async () => {
        throw new Error("no window to open into");
      },
    }).open();

    expect(result.ok).toBe(false);
    expect(!result.ok && result.error.message).toContain("no window");
  });

  it("says so when the browser has no options page API", async () => {
    const result = await createOptionsPage({}).open();

    expect(!result.ok && result.error.kind).toBe("unsupported");
  });
});
