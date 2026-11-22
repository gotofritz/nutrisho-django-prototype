import { describe, expect, it, vi } from "vitest";

import { createFakeStorage } from "./fake-storage";

describe("createFakeStorage", () => {
  it("gives back what was set, and forgets what was removed", async () => {
    const storage = createFakeStorage();

    await storage.set("clipping", { text: "basil" });
    const stored = await storage.get("clipping");
    await storage.remove("clipping");

    expect(stored).toEqual({ text: "basil" });
    expect(await storage.get("clipping")).toBeUndefined();
  });

  it("starts from what it is given, and shows what it holds", async () => {
    const storage = createFakeStorage({ settings: { apiKey: "nsh_x" } });

    expect(storage.written).toEqual({ settings: { apiKey: "nsh_x" } });
  });

  it("tells a watcher about a change to its key, and to no other", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();
    storage.onChanged("clipping", changed);

    await storage.set("settings", {});
    await storage.set("clipping", {});

    expect(changed).toHaveBeenCalledTimes(1);
  });

  // As `storage.local` and `storage.session` do: they keep a structured
  // clone, and refuse a Proxy such as Svelte's reactive state.
  it("keeps a copy, and refuses what the browser cannot clone", async () => {
    const storage = createFakeStorage();
    const value = { rows: ["1 lemon"] };

    await storage.set("drafts", value);
    expect(storage.written.drafts).toEqual(value);
    expect(storage.written.drafts).not.toBe(value);

    await expect(storage.set("drafts", new Proxy(value, {}))).rejects.toThrow(
      /could not be cloned/,
    );
  });

  it("can be made to refuse", async () => {
    const storage = createFakeStorage();
    storage.failWith(new Error("storage is full"));

    await expect(storage.set("clipping", {})).rejects.toThrow(
      "storage is full",
    );
    await expect(storage.get("clipping")).rejects.toThrow("storage is full");
  });
});
