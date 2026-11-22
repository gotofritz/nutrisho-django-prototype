import { describe, expect, it } from "vitest";

import { apiExample } from "../../tests/support/api-examples";

import {
  EMPTY_VOCABULARY,
  knows,
  knowsCuisine,
  knowsTag,
  parseVocabulary,
} from "./vocabulary";

const REPLY = apiExample("vocabulary.json").response.body as Record<
  string,
  unknown
>;

describe("parseVocabulary", () => {
  it("reads the server's example reply", () => {
    const parsed = parseVocabulary(REPLY);

    expect(parsed.ok).toBe(true);
    expect(parsed.ok && parsed.value.user).toBe("cook");
    expect(parsed.ok && parsed.value.ingredients[0]).toEqual({
      name: "aubergine",
      spellings: ["aubergines", "eggplant", "eggplants"],
    });
    expect(parsed.ok && parsed.value.cuisines).toContain("med.italy");
    expect(parsed.ok && parsed.value.limits.recipe_name).toBe(200);
  });

  it("keeps every section the example has, and nothing else", () => {
    const parsed = parseVocabulary(REPLY);

    expect(parsed.ok && Object.keys(parsed.value).sort()).toEqual(
      Object.keys(REPLY).sort(),
    );
  });

  // A later kind of data is a new section (plan 012, M4); an older clipper
  // must not refuse a reply because a newer server added one.
  it("ignores a section it does not know", () => {
    const parsed = parseVocabulary({ ...REPLY, nutrition: [] });

    expect(parsed.ok && parsed.value).not.toHaveProperty("nutrition");
  });

  it.each([
    ["no reply at all", null],
    ["a list", []],
    ["no user", { ...REPLY, user: undefined }],
    ["ingredients that are not a list", { ...REPLY, ingredients: {} }],
    [
      "an ingredient with no name",
      { ...REPLY, ingredients: [{ spellings: [] }] },
    ],
    [
      "a unit whose spellings are not strings",
      { ...REPLY, units: [{ name: "g", spellings: [1] }] },
    ],
    ["cuisines that are not strings", { ...REPLY, cuisines: [{}] }],
    [
      "limits that are not numbers",
      { ...REPLY, limits: { recipe_name: "200" } },
    ],
  ])("refuses %s", (_, body) => {
    const parsed = parseVocabulary(body);

    expect(!parsed.ok && parsed.error.kind).toBe("malformed-response");
  });

  it("has an empty library for nobody to start from", () => {
    expect(EMPTY_VOCABULARY).toEqual({
      user: "",
      ingredients: [],
      units: [],
      cuisines: [],
      tags: [],
      limits: {},
    });
  });
});

// Plan 012, D4: a name the lists do not hold is marked *new*, and the save
// makes it the user's own.
describe("knows", () => {
  const units = [{ name: "tbsp", spellings: ["tablespoon", "tablespoons"] }];

  it("knows a name by any of its spellings, ignoring case", () => {
    expect(knows(units, "tbsp")).toBe(true);
    expect(knows(units, "Tablespoons")).toBe(true);
  });

  it("ignores spaces around it and a trailing full stop, as the server does for units", () => {
    expect(knows(units, " tbsp. ")).toBe(true);
  });

  it("does not know any other name", () => {
    expect(knows(units, "handful")).toBe(false);
  });
});

// M8: a cuisine is a dotted path, or a bare name the server finds because
// only one node has it (`find_cuisine`).
describe("knowsCuisine", () => {
  const paths = [
    "med",
    "med.italy",
    "med.italy.sicily",
    "asia.thailand.north",
    "asia.vietnam.north",
  ];

  it("knows a whole path, ignoring case and spaces around it", () => {
    expect(knowsCuisine(paths, " Med.Italy ")).toBe(true);
  });

  it("knows a bare name only one node has", () => {
    expect(knowsCuisine(paths, "sicily")).toBe(true);
    expect(knowsCuisine(paths, "north")).toBe(false);
  });

  it("does not know any other name", () => {
    expect(knowsCuisine(paths, "med.italy.marche")).toBe(false);
  });
});

describe("knowsTag", () => {
  it("knows a tag in the list, ignoring case and spaces around it", () => {
    expect(knowsTag(["dinner"], " Dinner ")).toBe(true);
    expect(knowsTag(["dinner"], "lunch")).toBe(false);
  });
});
