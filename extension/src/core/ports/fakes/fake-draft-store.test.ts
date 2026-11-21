import { describe, expect, it } from "vitest";

import { EMPTY_DRAFTS, afterClip } from "../../drafts";
import { clippingFrom } from "../../clipping";
import { err, ok } from "../../result";
import { createFakeDraftStore } from "./fake-draft-store";

const DRAFTS = afterClip(
  EMPTY_DRAFTS,
  clippingFrom(
    {
      text: "basil",
      title: "Pesto",
      url: "https://example.test",
      warnings: [],
    },
    new Date("2026-11-20T09:30:00Z"),
  ),
  () => "draft-1",
);

describe("createFakeDraftStore", () => {
  it("holds no drafts to begin with", async () => {
    expect(await createFakeDraftStore().load()).toEqual(ok(EMPTY_DRAFTS));
  });

  it("gives back what was saved", async () => {
    const store = createFakeDraftStore();

    await store.save(DRAFTS);

    expect(await store.load()).toEqual(ok(DRAFTS));
    expect(store.saves).toBe(1);
  });

  // Browser storage keeps a structured clone, which refuses a Proxy, such as
  // Svelte's reactive state. The fake does the same, so the sidebar's tests
  // catch a draft that would not store.
  it("stores a copy, and refuses what browser storage cannot clone", async () => {
    const store = createFakeDraftStore();

    await store.save(DRAFTS);
    const loaded = await store.load();
    expect(loaded.ok && loaded.value).not.toBe(DRAFTS);

    const refused = await store.save(new Proxy(DRAFTS, {}));
    expect(!refused.ok && refused.error).toEqual({
      kind: "write-failed",
      message: expect.stringMatching(/could not be cloned/),
    });
  });

  it("can start with drafts", async () => {
    expect(await createFakeDraftStore(DRAFTS).load()).toEqual(ok(DRAFTS));
  });

  it("can fail the way storage does", async () => {
    const store = createFakeDraftStore();
    const failure = { kind: "write-failed" as const, message: "quota" };

    store.failWith(failure);

    expect(await store.save(DRAFTS)).toEqual(err(failure));
    expect(await store.load()).toEqual(err(failure));
  });
});
