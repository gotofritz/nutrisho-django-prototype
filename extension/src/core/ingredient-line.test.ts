import { describe, expect, it } from "vitest";

import { scanLine } from "./ingredient-line";
import { EMPTY_VOCABULARY, type Term, type Vocabulary } from "./vocabulary";

function term(name: string, ...spellings: string[]): Term {
  return { name, spellings };
}

function lists(ingredients: Term[], units: Term[] = []): Vocabulary {
  return { ...EMPTY_VOCABULARY, ingredients, units };
}

/** The scanned fields only, so each case reads as the plan's table does. */
function scanned(line: string, vocabulary: Vocabulary) {
  const { quantity, unit, ingredient, rest } = scanLine(line, vocabulary);
  return { quantity, unit, ingredient, rest };
}

// Plan 012, M7: the scan fills a field only when it is sure, and leaves every
// other word, in order, in *rest*. These three are its first tests.
describe("the plan's first lines", () => {
  const plan = lists([
    term("lemon", "lemons"),
    term("diced tomato", "diced tomatoes"),
  ]);

  it("reads `Juice of 1 lemon`", () => {
    expect(scanned("Juice of 1 lemon", plan)).toEqual({
      quantity: "1",
      unit: "",
      ingredient: "lemon",
      rest: "Juice of",
    });
  });

  it("reads `1 (14-ounce) can diced tomatoes`", () => {
    expect(scanned("1 (14-ounce) can diced tomatoes", plan)).toEqual({
      quantity: "",
      unit: "",
      ingredient: "diced tomato",
      rest: "1 (14-ounce) can",
    });
  });

  it("reads `A fresh basket of boletus`", () => {
    expect(scanned("A fresh basket of boletus", plan)).toEqual({
      quantity: "",
      unit: "",
      ingredient: "",
      rest: "A fresh basket of boletus",
    });
  });
});

describe("the ingredient", () => {
  it("is the longest name in the list that the line holds", () => {
    const vocabulary = lists([
      term("tomato", "tomatoes"),
      term("diced tomato", "diced tomatoes"),
    ]);

    expect(scanned("2 diced tomatoes", vocabulary).ingredient).toBe(
      "diced tomato",
    );
  });

  it("is stored in its canonical spelling, whatever the line says", () => {
    const vocabulary = lists([term("aubergine", "aubergines", "eggplant")]);

    expect(scanned("2 eggplant", vocabulary)).toMatchObject({
      quantity: "2",
      ingredient: "aubergine",
    });
  });

  it("ignores case and the punctuation around a word", () => {
    const vocabulary = lists([term("basil")]);

    expect(scanned("Basil, torn", vocabulary)).toMatchObject({
      ingredient: "basil",
      rest: "torn",
    });
  });

  it("matches whole words only", () => {
    const vocabulary = lists([term("egg", "eggs")]);

    expect(scanned("1 eggplant", vocabulary).ingredient).toBe("");
  });
});

describe("the unit", () => {
  const vocabulary = lists(
    [term("rigatoni"), term("sugar"), term("flour")],
    [term("g", "gram", "grams"), term("tbsp", "tablespoon"), term("fl oz")],
  );

  it("is a name from the list directly before the ingredient", () => {
    expect(scanned("400 grams rigatoni", vocabulary)).toEqual({
      quantity: "400",
      unit: "g",
      ingredient: "rigatoni",
      rest: "",
    });
  });

  it("ignores a unit's trailing full stop", () => {
    expect(scanned("2 tbsp. sugar", vocabulary)).toMatchObject({
      quantity: "2",
      unit: "tbsp",
      ingredient: "sugar",
    });
  });

  it("can be more than one word", () => {
    expect(scanned("4 fl oz flour", vocabulary)).toMatchObject({
      quantity: "4",
      unit: "fl oz",
    });
  });

  it("is not taken when a word stands between it and the ingredient", () => {
    expect(scanned("400 g of rigatoni", vocabulary)).toEqual({
      quantity: "",
      unit: "",
      ingredient: "rigatoni",
      rest: "400 g of",
    });
  });

  it("is not taken without an ingredient", () => {
    expect(scanned("400 g of something", vocabulary)).toMatchObject({
      unit: "",
      rest: "400 g of something",
    });
  });
});

describe("the quantity", () => {
  const vocabulary = lists(
    [term("flour"), term("lemon")],
    [term("cup", "cups")],
  );

  it.each([
    ["1.5 cups flour", "1.5"],
    ["1,5 cups flour", "1.5"],
    ["1/2 cup flour", "0.5"],
    ["½ cup flour", "0.5"],
    ["1½ cups flour", "1.5"],
    ["1 1/2 cups flour", "1.5"],
    ["1/3 cup flour", "0.33"],
    ["2.50 cups flour", "2.5"],
  ])("reads %s as %s", (line, quantity) => {
    expect(scanned(line, vocabulary)).toMatchObject({
      quantity,
      unit: "cup",
      ingredient: "flour",
      rest: "",
    });
  });

  it("leaves a range in rest", () => {
    expect(scanned("2-3 lemon", vocabulary)).toMatchObject({
      quantity: "",
      rest: "2-3",
    });
  });

  it("leaves a number too large to store in rest", () => {
    expect(scanned("100000 lemon", vocabulary)).toMatchObject({
      quantity: "",
      rest: "100000",
    });
  });
});

describe("a scanned row", () => {
  it("starts with the fields the scan does not fill empty", () => {
    expect(scanLine("1 lemon", lists([term("lemon")]))).toEqual({
      quantity: "1",
      unit: "",
      ingredient: "lemon",
      substitute: "",
      preparation: "",
      note: "",
      rest: "",
    });
  });

  it("keeps the words of rest as they were written", () => {
    expect(scanned("  Juice  of 1 lemon ", lists([term("lemon")])).rest).toBe(
      "Juice of",
    );
  });
});

describe("a whole number before a fraction", () => {
  it("joins a vulgar fraction written apart", () => {
    const vocabulary = lists([term("flour")], [term("cup", "cups")]);

    expect(scanned("1 ½ cups flour", vocabulary)).toMatchObject({
      quantity: "1.5",
      rest: "",
    });
  });

  it("does not join two whole numbers", () => {
    const vocabulary = lists([term("lemon", "lemons")]);

    expect(scanned("2 3 lemons", vocabulary)).toMatchObject({
      quantity: "3",
      rest: "2",
    });
  });
});
