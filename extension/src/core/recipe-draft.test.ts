import { describe, expect, it } from "vitest";

import { apiExample } from "../../tests/support/api-examples";

import { EMPTY_ROW } from "./ingredient-line";
import {
  addTo,
  checkDraft,
  isRecipeDraft,
  replace,
  savePath,
  startDraft,
  toDocument,
  updateRow,
  updateStep,
  withDetails,
  type RecipeDraft,
} from "./recipe-draft";
import { EMPTY_VOCABULARY, type Vocabulary } from "./vocabulary";

const ID = "01a1f5b5-dbe2-704a-b591-7ffbcff6762e";

const LISTS: Vocabulary = {
  ...EMPTY_VOCABULARY,
  ingredients: [
    { name: "lemon", spellings: ["lemons"] },
    { name: "aubergine", spellings: ["aubergines"] },
  ],
  units: [{ name: "g", spellings: ["grams"] }],
};

function draft(): RecipeDraft {
  return startDraft({
    id: ID,
    title: "Pasta alla Norma",
    url: "https://example.com/norma",
    now: "2026-11-20T09:30:00.000Z",
  });
}

describe("a new draft", () => {
  it("takes its name from the page's title and its source from the address", () => {
    expect(draft()).toEqual({
      id: ID,
      name: "Pasta alla Norma",
      blurb: "",
      servings: "",
      source: "https://example.com/norma",
      cuisine: "",
      tags: [],
      rows: [],
      steps: [],
      startedAt: "2026-11-20T09:30:00.000Z",
    });
  });

  it("is told from anything else that is stored", () => {
    expect(isRecipeDraft(draft())).toBe(true);
    expect(isRecipeDraft({ ...draft(), rows: "no" })).toBe(false);
    expect(isRecipeDraft(null)).toBe(false);
  });
});

describe("Add to and Replace", () => {
  it("adds to the name with a space, and replaces it on one line", () => {
    expect(addTo(draft(), "name", "with ricotta", LISTS).name).toBe(
      "Pasta alla Norma with ricotta",
    );
    expect(replace(draft(), "name", "Norma\nfrom Catania", LISTS).name).toBe(
      "Norma from Catania",
    );
  });

  it("adds to the blurb as a paragraph of its own", () => {
    const once = addTo(draft(), "blurb", "A Sicilian classic.", LISTS);

    expect(once.blurb).toBe("A Sicilian classic.");
    expect(addTo(once, "blurb", "Use ricotta salata.", LISTS).blurb).toBe(
      "A Sicilian classic.\n\nUse ricotta salata.",
    );
    expect(replace(once, "blurb", "Quick.", LISTS).blurb).toBe("Quick.");
  });

  it("scans each line sent to the ingredients into a row, skipping blank ones", () => {
    const rows = addTo(
      draft(),
      "ingredients",
      "2 aubergines\n\n400 grams rigatoni",
      LISTS,
    ).rows;

    expect(rows).toEqual([
      { ...EMPTY_ROW, quantity: "2", ingredient: "aubergine" },
      { ...EMPTY_ROW, rest: "400 grams rigatoni" },
    ]);
  });

  it("adds rows after the ones there, or replaces them all", () => {
    const once = addTo(draft(), "ingredients", "1 lemon", LISTS);

    expect(addTo(once, "ingredients", "2 lemons", LISTS).rows).toHaveLength(2);
    expect(replace(once, "ingredients", "2 lemons", LISTS).rows).toEqual([
      { ...EMPTY_ROW, quantity: "2", ingredient: "lemon" },
    ]);
  });

  it("makes a step of each line or paragraph", () => {
    const once = addTo(
      draft(),
      "steps",
      "Fry the aubergine.\n\nToss with the pasta.",
      LISTS,
    );

    expect(once.steps).toEqual(["Fry the aubergine.", "Toss with the pasta."]);
    expect(addTo(once, "steps", "Serve.", LISTS).steps).toHaveLength(3);
    expect(replace(once, "steps", "Serve.", LISTS).steps).toEqual(["Serve."]);
  });

  it("leaves the draft as it was when the text is blank", () => {
    const before = addTo(draft(), "steps", "Fry.", LISTS);

    expect(addTo(before, "steps", "  \n ", LISTS)).toBe(before);
    expect(replace(before, "name", " ", LISTS)).toBe(before);
  });
});

describe("editing", () => {
  it("changes one field of one row", () => {
    const before = addTo(draft(), "ingredients", "1 lemon\n2 lemons", LISTS);
    const after = updateRow(before, 1, { preparation: "zested", rest: "" });

    expect(after.rows[0]).toBe(before.rows[0]);
    expect(after.rows[1]).toEqual({
      ...EMPTY_ROW,
      quantity: "2",
      ingredient: "lemon",
      preparation: "zested",
    });
  });

  it("changes one step", () => {
    const before = addTo(draft(), "steps", "Fry.\nToss.", LISTS);

    expect(updateStep(before, 0, "Fry well.").steps).toEqual([
      "Fry well.",
      "Toss.",
    ]);
  });

  it("changes the name, blurb, servings and source", () => {
    expect(
      withDetails(draft(), { name: "Norma", servings: "4", blurb: "Good." }),
    ).toMatchObject({ name: "Norma", servings: "4", blurb: "Good." });
  });
});

describe("what stops a save", () => {
  const ready = withDetails(addTo(draft(), "ingredients", "1 lemon", LISTS), {
    servings: "4",
  });

  it("is nothing, for a draft with a name and every row named", () => {
    expect(checkDraft(ready)).toEqual([]);
  });

  it("is a missing name", () => {
    expect(checkDraft(withDetails(ready, { name: "  " }))).toEqual([
      { field: "name", message: "The recipe needs a name." },
    ]);
  });

  it("is a row with no ingredient, by its number", () => {
    const issues = checkDraft(
      addTo(ready, "ingredients", "a pinch of something", LISTS),
    );

    expect(issues).toEqual([
      { field: "rows.1.ingredient", message: "Row 2 has no ingredient." },
    ]);
  });

  it.each(["two", "1/2", "1.234", "100000", "-1"])(
    "is a quantity of %s",
    (quantity) => {
      expect(checkDraft(updateRow(ready, 0, { quantity }))).toEqual([
        {
          field: "rows.0.quantity",
          message:
            "The quantity in row 1 is not a number the recipe can hold, such as 2, 1.5 or 0.25.",
        },
      ]);
    },
  );

  it.each(["", "2", "0.25", "1,5"])("is not a quantity of '%s'", (quantity) => {
    expect(checkDraft(updateRow(ready, 0, { quantity }))).toEqual([]);
  });

  it.each(["0", "two", "1.5", "32768"])("is servings of %s", (servings) => {
    expect(checkDraft(withDetails(ready, { servings }))).toEqual([
      {
        field: "servings",
        message: "Servings must be a whole number from 1 to 32767.",
      },
    ]);
  });

  it("is not blank servings, which the server takes as 1", () => {
    expect(checkDraft(withDetails(ready, { servings: "" }))).toEqual([]);
  });
});

// The server's own example of a save: a draft holding that recipe is sent as
// exactly that request, so a change on either side fails a test.
describe("the save", () => {
  const example = apiExample("save.json");
  const norma: RecipeDraft = {
    ...draft(),
    servings: "4",
    cuisine: "med.italy",
    tags: ["dinner"],
    steps: ["Fry the aubergine.", "Toss with the pasta."],
    rows: [
      {
        ...EMPTY_ROW,
        quantity: "2",
        ingredient: "aubergines",
        preparation: "cubed",
      },
      { ...EMPTY_ROW, quantity: "400", unit: "g", ingredient: "rigatoni" },
      { ...EMPTY_ROW, unit: "handful", ingredient: "basil", note: "torn" },
    ],
  };

  it("posts to the path the server's example shows, under the draft's id", () => {
    expect(savePath(norma)).toBe(example.request.path);
  });

  it("sends the document the server's example shows", () => {
    expect(toDocument(norma)).toEqual(example.request.body);
  });

  it("saves what is left in rest in the row's note", () => {
    const row = {
      ...EMPTY_ROW,
      ingredient: "lemon",
      note: "unwaxed",
      rest: "Juice of",
    };
    const [group] = (toDocument({ ...norma, rows: [row] }) as DocumentShape)
      .recipes[0]!.ingredient_groups;

    expect(group!.items[0]).toMatchObject({ note: "unwaxed Juice of" });
  });

  it("sends a quantity with a decimal comma as the server reads it", () => {
    const row = { ...EMPTY_ROW, ingredient: "lemon", quantity: "1,5" };
    const [group] = (toDocument({ ...norma, rows: [row] }) as DocumentShape)
      .recipes[0]!.ingredient_groups;

    expect(group!.items[0]).toMatchObject({ quantity: "1.5" });
  });

  it("leaves servings out when blank, so the server takes its default", () => {
    const recipe = (toDocument({ ...norma, servings: "" }) as DocumentShape)
      .recipes[0]!;

    expect(recipe).not.toHaveProperty("servings");
  });
});

interface DocumentShape {
  recipes: { ingredient_groups: { items: Record<string, unknown>[] }[] }[];
}
