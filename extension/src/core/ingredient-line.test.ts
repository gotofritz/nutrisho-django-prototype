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

  // The plan left the 1 in rest; with no better candidate it is the quantity.
  it("reads `1 (14-ounce) can diced tomatoes`", () => {
    expect(scanned("1 (14-ounce) can diced tomatoes", plan)).toEqual({
      quantity: "1",
      unit: "",
      ingredient: "diced tomato",
      rest: "(14-ounce) can",
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
    [
      term("g", "gram", "grams"),
      term("tbsp", "tablespoon"),
      term("fl oz"),
      term("ml"),
    ],
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

  // `190g plain flour`: the words between an amount with its unit and the
  // ingredient describe it, and stay in rest.
  it("may stand apart from the ingredient, straight after its amount", () => {
    expect(scanned("400 g of rigatoni", vocabulary)).toEqual({
      quantity: "400",
      unit: "g",
      ingredient: "rigatoni",
      rest: "of",
    });
  });

  it("is taken with the amount nearest the ingredient", () => {
    expect(scanned("2 tbsp or 30 g sifted flour", vocabulary)).toMatchObject({
      quantity: "30",
      unit: "g",
      rest: "2 tbsp or sifted",
    });
  });

  it("keeps the nearest amount before it, when the amount is apart", () => {
    expect(scanned("2 heaped tbsp sugar", vocabulary)).toEqual({
      quantity: "2",
      unit: "tbsp",
      ingredient: "sugar",
      rest: "heaped",
    });
  });

  // `90ml dark maple syrup`: an ingredient the lists do not have yet.
  it("is taken with its amount at the start of a line without an ingredient", () => {
    expect(
      scanned("90ml dark maple syrup, plus extra to finish", vocabulary),
    ).toEqual({
      quantity: "90",
      unit: "ml",
      ingredient: "",
      rest: "dark maple syrup, plus extra to finish",
    });
  });

  it("leaves the amount that starts a line without an ingredient on its own", () => {
    expect(scanned("3 duck eggs", vocabulary)).toEqual({
      quantity: "3",
      unit: "",
      ingredient: "",
      rest: "duck eggs",
    });
  });

  it("is not taken elsewhere in a line without an ingredient", () => {
    expect(scanned("about 400 g of something", vocabulary)).toMatchObject({
      quantity: "",
      unit: "",
      rest: "about 400 g of something",
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

  // `2 large eggs`: with no unit, the nearest amount before the ingredient.
  it("is the nearest amount before the ingredient, when words stand between", () => {
    expect(scanned("2 large juicy lemon", vocabulary)).toEqual({
      quantity: "2",
      unit: "",
      ingredient: "lemon",
      rest: "large juicy",
    });
  });

  it("is not an amount after the ingredient", () => {
    expect(scanned("lemon, 2 of them", vocabulary)).toMatchObject({
      quantity: "",
      rest: "2 of them",
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

  it("keeps the commas of the words it takes in rest", () => {
    const vocabulary = lists([term("flour"), term("butter")], [term("g")]);

    expect(
      scanned("190g plain flour, plus extra for dusting", vocabulary),
    ).toEqual({
      quantity: "190",
      unit: "g",
      ingredient: "flour",
      rest: "plain, plus extra for dusting",
    });
    expect(scanned("110g cold unsalted butter, cubed", vocabulary).rest).toBe(
      "cold unsalted, cubed",
    );
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

// Some sites print an amount with no space before its unit.
describe("an amount written against its unit", () => {
  const vocabulary = lists(
    [term("milk"), term("flour"), term("lemon", "lemons")],
    [term("ml"), term("g", "gram", "grams")],
  );

  it.each([
    ["600ml milk", "600", "ml", "milk"],
    ["100g flour", "100", "g", "flour"],
    ["1.5g flour", "1.5", "g", "flour"],
    ["½g flour", "0.5", "g", "flour"],
  ])("reads %s", (line, quantity, unit, ingredient) => {
    expect(scanned(line, vocabulary)).toEqual({
      quantity,
      unit,
      ingredient,
      rest: "",
    });
  });

  it("keeps the word whole in rest when it is not taken", () => {
    expect(scanned("about 100g of something", vocabulary).rest).toBe(
      "about 100g of something",
    );
  });

  it("keeps the word whole in rest when what follows the number is not a unit", () => {
    expect(scanned("2x lemons", vocabulary)).toMatchObject({
      quantity: "",
      ingredient: "lemon",
      rest: "2x",
    });
  });
});
