import { describe, expect, it } from "vitest";

import { apiExample } from "../../tests/support/api-examples";

import { EMPTY_ROW } from "./ingredient-line";
import {
  addTo,
  checkDraft,
  groupFrom,
  isRecipeDraft,
  removeRow,
  replace,
  savePath,
  startDraft,
  toDocument,
  updateGroupName,
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
    { name: "sugar", spellings: [] },
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
      groups: [],
      steps: [],
      startedAt: "2026-11-20T09:30:00.000Z",
    });
  });

  it("is told from anything else that is stored", () => {
    expect(isRecipeDraft(draft())).toBe(true);
    expect(isRecipeDraft({ ...draft(), groups: "no" })).toBe(false);
    expect(isRecipeDraft({ ...draft(), steps: ["Fry."] })).toBe(false);
    expect(isRecipeDraft(null)).toBe(false);
  });
});

// Plan 012, D7: a line among the ingredients can be a group's name. The
// first line of a group is taken for one when nothing in it is known.
describe("an ingredient group from text", () => {
  it("scans each line into a row, skipping blank ones", () => {
    expect(groupFrom("2 aubergines\n\n400 grams rigatoni", LISTS)).toEqual({
      name: "",
      rows: [
        { ...EMPTY_ROW, quantity: "2", ingredient: "aubergine" },
        { ...EMPTY_ROW, quantity: "400", unit: "g", rest: "rigatoni" },
      ],
    });
  });

  it("takes a first line it knows nothing in for the group's name", () => {
    expect(groupFrom("For the syrup:\n100 g sugar\n1 lemon", LISTS)).toEqual({
      name: "For the syrup",
      rows: [
        { ...EMPTY_ROW, quantity: "100", unit: "g", ingredient: "sugar" },
        { ...EMPTY_ROW, quantity: "1", ingredient: "lemon" },
      ],
    });
  });

  it("keeps a lone line as a row, not a name", () => {
    expect(groupFrom("A fresh basket of boletus", LISTS)).toEqual({
      name: "",
      rows: [{ ...EMPTY_ROW, rest: "A fresh basket of boletus" }],
    });
  });

  // Some sites put `, cubed` in an element of its own, so it is copied as a
  // line of its own.
  it("joins a line that starts with a comma to the line before", () => {
    expect(groupFrom("1 lemon\n, zested", LISTS).rows).toEqual([
      { ...EMPTY_ROW, quantity: "1", ingredient: "lemon", rest: "zested" },
    ]);
  });

  it("keeps the amounts of ingredients the lists do not have", () => {
    const custard = groupFrom(
      "For the custard\n\n90ml dark maple syrup, plus extra to finish\n\n6 egg yolks\n40g sugar",
      { ...LISTS, units: [...LISTS.units, { name: "ml", spellings: [] }] },
    );

    expect(custard.name).toBe("For the custard");
    expect(custard.rows).toEqual([
      {
        ...EMPTY_ROW,
        quantity: "90",
        unit: "ml",
        rest: "dark maple syrup, plus extra to finish",
      },
      { ...EMPTY_ROW, quantity: "6", rest: "egg yolks" },
      { ...EMPTY_ROW, quantity: "40", unit: "g", ingredient: "sugar" },
    ]);
  });

  it("names nothing when the first line starts with an amount", () => {
    expect(groupFrom("90 g maple syrup\n1 lemon", LISTS).name).toBe("");
  });

  it("names nothing when the first line holds an ingredient", () => {
    expect(groupFrom("1 lemon\nFor the syrup:", LISTS).name).toBe("");
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

  it("adds a group after the ones there, or replaces them all", () => {
    const once = addTo(draft(), "group", "1 lemon", LISTS);
    const twice = addTo(once, "group", "For the syrup:\n100 g sugar", LISTS);

    expect(twice.groups.map((group) => group.name)).toEqual([
      "",
      "For the syrup",
    ]);
    expect(replace(twice, "group", "2 lemons", LISTS).groups).toEqual([
      {
        name: "",
        rows: [{ ...EMPTY_ROW, quantity: "2", ingredient: "lemon" }],
      },
    ]);
  });

  it("makes a step of each line or paragraph", () => {
    const once = addTo(
      draft(),
      "steps",
      "Fry the aubergine.\n\nToss with the pasta.",
      LISTS,
    );

    expect(once.steps).toEqual([
      { title: "", text: "Fry the aubergine." },
      { title: "", text: "Toss with the pasta." },
    ]);
    expect(addTo(once, "steps", "Serve.", LISTS).steps).toHaveLength(3);
    expect(replace(once, "steps", "Serve.", LISTS).steps).toEqual([
      { title: "", text: "Serve." },
    ]);
  });

  it("leaves the draft as it was when the text is blank", () => {
    const before = addTo(draft(), "steps", "Fry.", LISTS);

    expect(addTo(before, "steps", "  \n ", LISTS)).toBe(before);
    expect(replace(before, "name", " ", LISTS)).toBe(before);
  });
});

describe("editing", () => {
  const two = addTo(
    addTo(draft(), "group", "1 lemon\n2 lemons", LISTS),
    "group",
    "Syrup:\n1 lemon",
    LISTS,
  );

  it("changes one field of one row", () => {
    const after = updateRow(two, 0, 1, { preparation: "zested", rest: "" });

    expect(after.groups[0]!.rows[0]).toBe(two.groups[0]!.rows[0]);
    expect(after.groups[1]).toBe(two.groups[1]);
    expect(after.groups[0]!.rows[1]).toEqual({
      ...EMPTY_ROW,
      quantity: "2",
      ingredient: "lemon",
      preparation: "zested",
    });
  });

  it("renames a group", () => {
    expect(updateGroupName(two, 1, "For the syrup").groups[1]!.name).toBe(
      "For the syrup",
    );
  });

  it("changes one step, its title or its text", () => {
    const before = addTo(draft(), "steps", "Fry.\nToss.", LISTS);
    const after = updateStep(before, 0, { text: "Fry well." });

    expect(after.steps).toEqual([
      { title: "", text: "Fry well." },
      { title: "", text: "Toss." },
    ]);
    expect(updateStep(after, 1, { title: "To serve" }).steps[1]).toEqual({
      title: "To serve",
      text: "Toss.",
    });
  });

  it("removes one row, and keeps its group", () => {
    const after = removeRow(two, 0, 0);

    expect(after.groups[0]!.rows).toEqual([two.groups[0]!.rows[1]]);
    expect(after.groups[1]).toBe(two.groups[1]);
    expect(removeRow(after, 0, 0).groups[0]!.rows).toEqual([]);
  });

  it("changes the name, blurb, servings and source", () => {
    expect(
      withDetails(draft(), { name: "Norma", servings: "4", blurb: "Good." }),
    ).toMatchObject({ name: "Norma", servings: "4", blurb: "Good." });
  });
});

describe("what stops a save", () => {
  const ready = withDetails(addTo(draft(), "group", "1 lemon", LISTS), {
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
      replace(ready, "group", "1 lemon\na pinch of something", LISTS),
    );

    expect(issues).toEqual([
      {
        field: "groups.0.rows.1.ingredient",
        message: "Row 2 has no ingredient.",
      },
    ]);
  });

  it("names the group too, when there is more than one", () => {
    const issues = checkDraft(
      addTo(ready, "group", "Syrup:\na pinch of something", LISTS),
    );

    expect(issues).toEqual([
      {
        field: "groups.1.rows.0.ingredient",
        message: "Row 1 of Syrup has no ingredient.",
      },
    ]);
  });

  it.each(["two", "1/2", "1.234", "100000", "-1"])(
    "is a quantity of %s",
    (quantity) => {
      expect(checkDraft(updateRow(ready, 0, 0, { quantity }))).toEqual([
        {
          field: "groups.0.rows.0.quantity",
          message:
            "The quantity in row 1 is not a number the recipe can hold, such as 2, 1.5 or 0.25.",
        },
      ]);
    },
  );

  it.each(["", "2", "0.25", "1,5"])("is not a quantity of '%s'", (quantity) => {
    expect(checkDraft(updateRow(ready, 0, 0, { quantity }))).toEqual([]);
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
    steps: [
      { title: "", text: "Fry the aubergine." },
      { title: "", text: "Toss with the pasta." },
    ],
    groups: [
      {
        name: "",
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
      },
    ],
  };

  it("posts to the path the server's example shows, under the draft's id", () => {
    expect(savePath(norma)).toBe(example.request.path);
  });

  it("sends the document the server's example shows", () => {
    expect(toDocument(norma)).toEqual(example.request.body);
  });

  it("sends each step under its title", () => {
    const titled = updateStep(norma, 0, { title: "The aubergine" });

    expect((toDocument(titled) as DocumentShape).recipes[0]!.steps[0]).toEqual({
      step_title: "The aubergine",
      step_text: "Fry the aubergine.",
    });
  });

  it("sends each group under its name", () => {
    const two = addTo(norma, "group", "For the syrup:\n100 g sugar", LISTS);

    expect(
      (toDocument(two) as DocumentShape).recipes[0]!.ingredient_groups.map(
        (group) => group.group_name,
      ),
    ).toEqual(["", "For the syrup"]);
  });

  it("saves what is left in rest in the row's note", () => {
    const row = {
      ...EMPTY_ROW,
      ingredient: "lemon",
      note: "unwaxed",
      rest: "Juice of",
    };
    const [group] = (
      toDocument({
        ...norma,
        groups: [{ name: "", rows: [row] }],
      }) as DocumentShape
    ).recipes[0]!.ingredient_groups;

    expect(group!.items[0]).toMatchObject({ note: "unwaxed Juice of" });
  });

  it("sends a quantity with a decimal comma as the server reads it", () => {
    const row = { ...EMPTY_ROW, ingredient: "lemon", quantity: "1,5" };
    const [group] = (
      toDocument({
        ...norma,
        groups: [{ name: "", rows: [row] }],
      }) as DocumentShape
    ).recipes[0]!.ingredient_groups;

    expect(group!.items[0]).toMatchObject({ quantity: "1.5" });
  });

  it("leaves servings out when blank, so the server takes its default", () => {
    const recipe = (toDocument({ ...norma, servings: "" }) as DocumentShape)
      .recipes[0]!;

    expect(recipe).not.toHaveProperty("servings");
  });
});

interface DocumentShape {
  recipes: {
    ingredient_groups: {
      group_name: string;
      items: Record<string, unknown>[];
    }[];
    steps: { step_title: string; step_text: string }[];
  }[];
}
