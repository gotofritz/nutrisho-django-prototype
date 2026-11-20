import { describe, expect, it } from "vitest";

import { clippingFrom } from "@/core/clipping";
import { EMPTY_DRAFTS, afterClip } from "@/core/drafts";

import { DRAFTS_KEY, createStoredDrafts } from "./draft-store";
import { createFakeStorage } from "./fakes/fake-storage";

const DRAFTS = afterClip(
  EMPTY_DRAFTS,
  clippingFrom(
    {
      text: "1 lemon",
      title: "Lemon tart",
      url: "https://example.test/tart",
      warnings: [],
    },
    new Date("2026-11-20T09:30:00Z"),
  ),
  () => "01a1f5b5-dbe2-704a-b591-7ffbcff6762e",
);

describe("the stored drafts", () => {
  it("round-trip through storage, so a draft survives the sidebar closing", async () => {
    const storage = createFakeStorage();

    expect(await createStoredDrafts(storage).save(DRAFTS)).toEqual({
      ok: true,
      value: undefined,
    });
    expect(await createStoredDrafts(storage).load()).toEqual({
      ok: true,
      value: DRAFTS,
    });
  });

  it("are none until something is clipped", async () => {
    expect(await createStoredDrafts(createFakeStorage()).load()).toEqual({
      ok: true,
      value: EMPTY_DRAFTS,
    });
  });

  it("say so when what is stored is not drafts", async () => {
    const storage = createFakeStorage({ [DRAFTS_KEY]: { drafts: "none" } });

    const loaded = await createStoredDrafts(storage).load();

    expect(!loaded.ok && loaded.error.kind).toBe("malformed-stored-value");
  });

  it("report storage refusing, rather than throwing", async () => {
    const storage = createFakeStorage();
    storage.failWith(new Error("storage is full"));
    const drafts = createStoredDrafts(storage);

    expect(await drafts.save(DRAFTS)).toEqual({
      ok: false,
      error: { kind: "write-failed", message: "storage is full" },
    });
    expect(await drafts.load()).toEqual({
      ok: false,
      error: { kind: "read-failed", message: "storage is full" },
    });
  });
});
