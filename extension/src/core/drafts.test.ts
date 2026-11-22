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
import { EMPTY_ROW } from "./ingredient-line";
import { withDetails, type RecipeDraft } from "./recipe-draft";
import { EMPTY_VOCABULARY, type Vocabulary } from "./vocabulary";

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

const LISTS: Vocabulary = {
  ...EMPTY_VOCABULARY,
  ingredients: [{ name: "lemon", spellings: ["lemons"] }],
};

const NORMA = clip(
  "https://example.com/norma",
  "2026-11-20T09:00:00Z",
  "Norma",
);
const RAGU = clip("https://example.com/ragu", "2026-11-20T09:05:00Z", "Ragù");

describe("a clipping", () => {
  it("starts the first draft, named after the page", () => {
    const drafts = afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS);

    expect(drafts.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(currentDraft(drafts)).toMatchObject({
      id: "a",
      name: "Norma",
      source: NORMA.url,
      startedAt: NORMA.clippedAt,
    });
  });

  it("from the same page keeps the draft it has", () => {
    const once = afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS);
    const again = afterClip(
      once,
      { ...NORMA, clippedAt: "2026-11-20T09:01:00.000Z" },
      ids("b"),
      LISTS,
    );

    expect(again.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(again.current).toBe("a");
  });

  it("from another page starts a new draft, and keeps the earlier one listed", () => {
    const drafts = afterClip(
      afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS),
      RAGU,
      ids("b"),
      LISTS,
    );

    expect(drafts.drafts.map((draft) => draft.id)).toEqual(["a", "b"]);
    expect(drafts.current).toBe("b");
  });

  it("from a page with a draft already goes back to that draft", () => {
    const both = afterClip(
      afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS),
      RAGU,
      ids("b"),
      LISTS,
    );
    const back = afterClip(
      both,
      { ...NORMA, clippedAt: "2026-11-20T09:10:00.000Z" },
      ids("c"),
      LISTS,
    );

    expect(back.drafts.map((draft) => draft.id)).toEqual(["a", "b"]);
    expect(back.current).toBe("a");
  });

  // The source is the user's to change (say, to where a saved page first
  // came from); clips from the page still belong to the draft.
  it("from the same page keeps the draft, whatever its source now says", () => {
    const once = afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS);
    const moved = withDraft(
      once,
      withDetails(currentDraft(once)!, { source: "https://example.org/x" }),
    );
    const again = afterClip(
      moved,
      { ...NORMA, clippedAt: "2026-11-20T09:01:00.000Z" },
      ids("b"),
      LISTS,
    );

    expect(again.drafts.map((draft) => draft.id)).toEqual(["a"]);
    expect(currentDraft(again)?.source).toBe("https://example.org/x");
  });

  it("goes back to a draft stored before it kept the page apart from the source", () => {
    const older: RecipeDraft = {
      ...currentDraft(afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS))!,
    };
    delete (older as { clippedFrom?: string }).clippedFrom;
    const held = afterClip(
      { drafts: [older], current: "a", saved: {} },
      NORMA,
      ids("b"),
      LISTS,
    );

    expect(held.drafts.map((draft) => draft.id)).toEqual(["a"]);
  });

  it("is applied once, however often the sidebar reads it", () => {
    const once = afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS);
    const discarded = discard(once, "a");

    expect(afterClip(discarded, NORMA, ids("b"), LISTS)).toBe(discarded);
  });

  it("drops the drafts already saved when it starts a new one", () => {
    const saved = markSaved(
      afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS),
      "a",
      {
        openUrl: "http://localhost:8987/recipes/a/?edit=1",
        name: "Norma",
        created: true,
        renamed: false,
        inTrash: false,
        warnings: [],
      },
    );

    expect(
      afterClip(saved, RAGU, ids("b"), LISTS).drafts.map((draft) => draft.id),
    ).toEqual(["b"]);
  });
});

// The right-click submenu sends the text on as well as to the clipboard:
// the title replaces the name, the rest add to what is there.
describe("a clipping sent somewhere", () => {
  function sent(target: Clipping["target"], text: string): Clipping {
    return clippingFrom(
      { text, title: "Norma", url: "https://example.com/norma", warnings: [] },
      new Date("2026-11-20T09:00:00Z"),
      target,
    );
  }

  it("replaces the name with the title", () => {
    const drafts = afterClip(
      EMPTY_DRAFTS,
      sent("name", "Pasta alla Norma"),
      ids("a"),
      LISTS,
    );

    expect(currentDraft(drafts)?.name).toBe("Pasta alla Norma");
  });

  it("adds a group of ingredients, scanned against the lists", () => {
    const drafts = afterClip(
      EMPTY_DRAFTS,
      sent("group", "2 lemons"),
      ids("a"),
      LISTS,
    );

    expect(currentDraft(drafts)?.groups).toEqual([
      {
        name: "",
        rows: [{ ...EMPTY_ROW, quantity: "2", ingredient: "lemon" }],
      },
    ]);
  });

  it("adds to the blurb and the steps of the draft it lands in", () => {
    const once = afterClip(
      EMPTY_DRAFTS,
      sent("steps", "Fry."),
      ids("a"),
      LISTS,
    );
    const twice = afterClip(
      once,
      { ...sent("steps", "Toss."), clippedAt: "2026-11-20T09:01:00.000Z" },
      ids("b"),
      LISTS,
    );

    expect(currentDraft(twice)?.steps.map((step) => step.text)).toEqual([
      "Fry.",
      "Toss.",
    ]);
    expect(
      currentDraft(
        afterClip(EMPTY_DRAFTS, sent("blurb", "Sicilian."), ids("a"), LISTS),
      )?.blurb,
    ).toBe("Sicilian.");
  });

  it("adds ingredients to the open group", () => {
    const grouped = afterClip(
      EMPTY_DRAFTS,
      sent("group", "1 lemon"),
      ids("a"),
      LISTS,
    );
    const more = afterClip(
      grouped,
      {
        ...sent("ingredient", "2 lemons"),
        clippedAt: "2026-11-20T09:01:00.000Z",
      },
      ids("b"),
      LISTS,
    );

    expect(currentDraft(more)?.groups).toHaveLength(1);
    expect(currentDraft(more)?.groups[0]?.rows).toHaveLength(2);
  });

  it("leaves the draft alone when sent to the clipboard only", () => {
    const drafts = afterClip(
      EMPTY_DRAFTS,
      sent("clipboard", "2 lemons"),
      ids("a"),
      LISTS,
    );

    expect(currentDraft(drafts)).toMatchObject({
      name: "Norma",
      groups: [],
      steps: [],
    });
  });
});

describe("the list of drafts", () => {
  const both = afterClip(
    afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS),
    RAGU,
    ids("b"),
    LISTS,
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
    const drafts: Drafts = afterClip(EMPTY_DRAFTS, NORMA, ids("a"), LISTS);

    expect(isDrafts(drafts)).toBe(true);
    expect(isDrafts(EMPTY_DRAFTS)).toBe(true);
    expect(isDrafts({ ...drafts, drafts: [{}] })).toBe(false);
    expect(isDrafts("drafts")).toBe(false);
  });
});
