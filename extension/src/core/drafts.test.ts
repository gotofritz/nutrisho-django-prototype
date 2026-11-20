import { describe, expect, it } from "vitest";

import { clippingFrom, type Clipping } from "./clipping";
import {
  EMPTY_DRAFTS,
  afterClip,
  choose,
  currentDraft,
  discard,
  isDrafts,
  markSaved,
  withDraft,
  type Drafts,
} from "./drafts";
import { withDetails } from "./recipe-draft";

function clip(url: string, at: string, title = "A page"): Clipping {
  return clippingFrom(
    { text: "1 lemon", title, url, warnings: [] },
    new Date(at),
  );
}

function ids(...made: string[]): () => string {
  const queue = [...made];
  return () => queue.shift() ?? "no-more-ids";
}

const NORMA = clip(
  "https://example.com/norma",
  "2026-11-20T09:00:00Z",
  "Norma",
);
const RAGU = clip("https://example.com/ragu", "2026-11-20T09:05:00Z", "Ragù");

describe("a clipping", () => {
  it("starts the first draft, named after the page", () => {
    const drafts = afterClip(EMPTY_DRAFTS, NORMA, ids("a"));

    expect(drafts.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(currentDraft(drafts)).toMatchObject({
      id: "a",
      name: "Norma",
      source: NORMA.url,
      startedAt: NORMA.clippedAt,
    });
  });

  it("from the same page keeps the draft it has", () => {
    const once = afterClip(EMPTY_DRAFTS, NORMA, ids("a"));
    const again = afterClip(
      once,
      { ...NORMA, clippedAt: "2026-11-20T09:01:00.000Z" },
      ids("b"),
    );

    expect(again.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(again.current).toBe("a");
  });

  it("from another page starts a new draft, and keeps the earlier one listed", () => {
    const drafts = afterClip(
      afterClip(EMPTY_DRAFTS, NORMA, ids("a")),
      RAGU,
      ids("b"),
    );

    expect(drafts.drafts.map((draft) => draft.id)).toEqual(["a", "b"]);
    expect(drafts.current).toBe("b");
  });

  it("from a page with a draft already goes back to that draft", () => {
    const both = afterClip(
      afterClip(EMPTY_DRAFTS, NORMA, ids("a")),
      RAGU,
      ids("b"),
    );
    const back = afterClip(
      both,
      { ...NORMA, clippedAt: "2026-11-20T09:10:00.000Z" },
      ids("c"),
    );

    expect(back.drafts.map((draft) => draft.id)).toEqual(["a", "b"]);
    expect(back.current).toBe("a");
  });

  it("is applied once, however often the sidebar reads it", () => {
    const once = afterClip(EMPTY_DRAFTS, NORMA, ids("a"));
    const discarded = discard(once, "a");

    expect(afterClip(discarded, NORMA, ids("b"))).toBe(discarded);
  });

  it("drops the drafts already saved when it starts a new one", () => {
    const saved = markSaved(afterClip(EMPTY_DRAFTS, NORMA, ids("a")), "a", {
      openUrl: "http://localhost:8987/recipes/a/?edit=1",
      name: "Norma",
      created: true,
      renamed: false,
      inTrash: false,
      warnings: [],
    });

    expect(
      afterClip(saved, RAGU, ids("b")).drafts.map((draft) => draft.id),
    ).toEqual(["b"]);
  });
});

describe("the list of drafts", () => {
  const both = afterClip(
    afterClip(EMPTY_DRAFTS, NORMA, ids("a")),
    RAGU,
    ids("b"),
  );

  it("can go back to an earlier draft", () => {
    expect(currentDraft(choose(both, "a"))?.id).toBe("a");
  });

  it("ignores a draft it does not hold", () => {
    expect(choose(both, "nope")).toBe(both);
  });

  it("discards a draft, and moves to the last one left", () => {
    const left = discard(both, "b");

    expect(left.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(left.current).toBe("a");
    expect(currentDraft(discard(left, "a"))).toBeUndefined();
  });

  it("keeps an edit to one draft", () => {
    const edited = withDraft(
      both,
      withDetails(currentDraft(both)!, { name: "Ragù bolognese" }),
    );

    expect(edited.drafts.map((draft) => draft.name)).toEqual([
      "Norma",
      "Ragù bolognese",
    ]);
  });
});

describe("what is stored", () => {
  it("is told from anything else", () => {
    const drafts: Drafts = afterClip(EMPTY_DRAFTS, NORMA, ids("a"));

    expect(isDrafts(drafts)).toBe(true);
    expect(isDrafts(EMPTY_DRAFTS)).toBe(true);
    expect(isDrafts({ ...drafts, drafts: [{}] })).toBe(false);
    expect(isDrafts("drafts")).toBe(false);
  });
});
