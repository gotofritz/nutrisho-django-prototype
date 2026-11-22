import { describe, expect, it } from "vitest";

import { clippingFrom } from "../../clipping";
import { isErr, isOk } from "../../result";
import { createFakeClippingStore } from "./fake-clipping-store";

const CLIPPING = clippingFrom(
  { text: "basil", title: "Pesto", url: "https://example.test", warnings: [] },
  new Date("2026-11-20T09:30:00Z"),
);

describe("createFakeClippingStore", () => {
  it("has nothing stored to begin with", async () => {
    const result = await createFakeClippingStore().load();

    expect(isOk(result) && result.value).toBe(undefined);
  });

  it("gives back what was saved, and forgets it when cleared", async () => {
    const store = createFakeClippingStore();

    await store.save(CLIPPING);
    const loaded = await store.load();
    await store.clear();
    const afterClear = await store.load();

    expect(isOk(loaded) && loaded.value).toEqual(CLIPPING);
    expect(isOk(afterClear) && afterClear.value).toBe(undefined);
  });

  it("can be driven into failure and reports it in the port's error shape", async () => {
    const store = createFakeClippingStore(CLIPPING);
    store.failWith({ kind: "write-failed", message: "storage is full" });

    const saved = await store.save(CLIPPING);
    const loaded = await store.load();

    expect(isErr(saved) && saved.error.kind).toBe("write-failed");
    expect(isErr(loaded)).toBe(true);
  });
});
