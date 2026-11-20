import { browser } from "wxt/browser";
import { describe, expect, it, vi } from "vitest";

import { createStorage } from "./storage";

describe("storage", () => {
  it("round-trips a value through the extension store", async () => {
    const storage = createStorage();

    await storage.set("deck", "Default");

    await expect(storage.get<string>("deck")).resolves.toBe("Default");
  });

  it("reports a missing key as undefined rather than throwing", async () => {
    await expect(createStorage().get("never-written")).resolves.toBeUndefined();
  });

  it("removes a key", async () => {
    const storage = createStorage();
    await storage.set("deck", "Default");

    await storage.remove("deck");

    await expect(storage.get("deck")).resolves.toBeUndefined();
  });

  it("writes where the browser can read it back after the background unloads", async () => {
    await createStorage().set("deck", "Default");

    await expect(browser.storage.local.get("deck")).resolves.toEqual({
      deck: "Default",
    });
  });
});

// The sidebar has to notice a clipping written by a gesture while it was
// already open: it persists per window on Firefox, so that is the common case
// after the first clip.
describe("storage changes", () => {
  it("tells a watcher when its key is written", async () => {
    const storage = createStorage();
    const changed = vi.fn();
    storage.onChanged("clipping", changed);

    await storage.set("clipping", { text: "basil" });

    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("ignores writes to other keys", async () => {
    const storage = createStorage();
    const changed = vi.fn();
    storage.onChanged("clipping", changed);

    await storage.set("settings", { defaultDeck: "Default" });

    expect(changed).not.toHaveBeenCalled();
  });

  it("tells a watcher when its key is removed", async () => {
    const storage = createStorage();
    await storage.set("clipping", { text: "basil" });
    const changed = vi.fn();
    storage.onChanged("clipping", changed);

    await storage.remove("clipping");

    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("stops telling it once the subscription is disposed", async () => {
    const storage = createStorage();
    const changed = vi.fn();

    storage.onChanged("clipping", changed)();
    await storage.set("clipping", { text: "basil" });

    expect(changed).not.toHaveBeenCalled();
  });
});
