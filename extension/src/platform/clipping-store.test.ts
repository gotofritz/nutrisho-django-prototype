import { describe, expect, it, vi } from "vitest";

import { clippingFrom } from "@/core/clipping";

import {
  CLIPPING_KEY,
  createStoredClipping,
  watchClipping,
} from "./clipping-store";
import { createFakeStorage } from "./fakes/fake-storage";

const CLIPPING = clippingFrom(
  {
    text: "2 aubergines\n1 tbsp olive oil",
    title: "Melanzane",
    url: "https://example.test/melanzane",
    warnings: [],
  },
  new Date("2026-11-20T09:30:00Z"),
);

describe("the stored clipping", () => {
  it("round-trips through storage", async () => {
    const clippings = createStoredClipping(createFakeStorage());

    expect(await clippings.save(CLIPPING)).toEqual({
      ok: true,
      value: undefined,
    });
    expect(await clippings.load()).toEqual({ ok: true, value: CLIPPING });
  });

  it("is nothing until something is clipped", async () => {
    expect(await createStoredClipping(createFakeStorage()).load()).toEqual({
      ok: true,
      value: undefined,
    });
  });

  it("is gone once cleared", async () => {
    const storage = createFakeStorage({ [CLIPPING_KEY]: CLIPPING });

    await createStoredClipping(storage).clear();

    expect(storage.written).toEqual({});
  });

  it("says so when what is stored is not a clipping", async () => {
    const storage = createFakeStorage({ [CLIPPING_KEY]: { deck: "Default" } });

    const loaded = await createStoredClipping(storage).load();

    expect(!loaded.ok && loaded.error.kind).toBe("malformed-stored-value");
  });

  it("reports storage refusing, rather than throwing", async () => {
    const storage = createFakeStorage();
    storage.failWith(new Error("storage is full"));
    const clippings = createStoredClipping(storage);

    expect(await clippings.save(CLIPPING)).toEqual({
      ok: false,
      error: { kind: "write-failed", message: "storage is full" },
    });
    expect(await clippings.load()).toEqual({
      ok: false,
      error: { kind: "read-failed", message: "storage is full" },
    });
    expect((await clippings.clear()).ok).toBe(false);
  });
});

describe("watchClipping", () => {
  // The sidebar is usually open already when the next capture happens.
  it("tells the sidebar about a clipping written by another context", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();
    watchClipping(storage, changed);

    await createStoredClipping(storage).save(CLIPPING);

    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("stops telling it once disposed", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();

    watchClipping(storage, changed)();
    await createStoredClipping(storage).save(CLIPPING);

    expect(changed).not.toHaveBeenCalled();
  });
});
