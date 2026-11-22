import { describe, expect, it } from "vitest";

import { EMPTY_ROW, type IngredientRow } from "./ingredient-line";
import {
  MODEL_INSTRUCTION,
  describeSplit,
  lineOf,
  numbered,
  readModelAnswer,
  rowsSchema,
} from "./model-answer";

const LINES = ["2 tbsp olive oil", "1 onion, finely chopped"];

/** What the built-in scan made of LINES. */
const BUILT_IN: readonly IngredientRow[] = [
  { ...EMPTY_ROW, quantity: "2", unit: "tbsp", ingredient: "olive oil" },
  { ...EMPTY_ROW, quantity: "1", rest: "onion, finely chopped" },
];

const GOOD = {
  rows: [
    { ...EMPTY_ROW, quantity: "2", unit: "tbsp", ingredient: "olive oil" },
    {
      ...EMPTY_ROW,
      quantity: "1",
      ingredient: "onion",
      preparation: "finely chopped",
    },
  ],
};

// Plan 012, M13 (#181): nothing the model answers is shown as if it were
// right unless it passes these checks.
describe("readModelAnswer", () => {
  it("takes rows that split their lines", () => {
    expect(readModelAnswer(LINES, GOOD, BUILT_IN)).toEqual({
      ok: true,
      value: { rows: GOOD.rows, kept: [], missed: [], translated: [] },
    });
  });

  it("reads a missing field as empty", () => {
    const answer = {
      rows: [
        { quantity: "2", unit: "tbsp", ingredient: "olive oil" },
        GOOD.rows[1],
      ],
    };

    const read = readModelAnswer(LINES, answer, BUILT_IN);

    expect(read.ok && read.value.rows[0]).toEqual(GOOD.rows[0]);
  });

  it("ignores case and spacing when it looks for a field in its line", () => {
    const read = readModelAnswer(
      ["2 Tbsp  Olive Oil"],
      { rows: [{ quantity: "2", unit: "tbsp", ingredient: "olive oil" }] },
      [EMPTY_ROW],
    );

    expect(read.ok && read.value.kept).toEqual([]);
  });

  it.each([
    ["not an object"],
    [{ rows: "2 tbsp" }],
    [{ rows: [GOOD.rows[0], { ...GOOD.rows[1], unit: 3 }] }],
    [{ rows: [GOOD.rows[0], null] }],
  ])("refuses an answer of the wrong shape: %j", (answer) => {
    const read = readModelAnswer(LINES, answer, BUILT_IN);

    expect(read).toEqual({
      ok: false,
      error: "The model's answer was not in the shape asked for.",
    });
  });

  it("refuses an answer with a row too many or too few", () => {
    expect(
      readModelAnswer(LINES, { rows: [...GOOD.rows, GOOD.rows[0]] }, BUILT_IN),
    ).toEqual({
      ok: false,
      error: "The model answered 3 rows for 2 lines.",
    });
  });

  // One invented word does not cost the whole group.
  it("keeps the built-in scan of a row with a field its line does not hold", () => {
    const answer = {
      rows: [GOOD.rows[0], { ...GOOD.rows[1], ingredient: "shallot" }],
    };

    expect(readModelAnswer(LINES, answer, BUILT_IN)).toEqual({
      ok: true,
      value: {
        rows: [GOOD.rows[0], BUILT_IN[1]],
        kept: [1],
        missed: [],
        translated: [],
      },
    });
  });

  it.each(["0.5", "400", "1.25"])(
    "takes a quantity written as a number: %s",
    (quantity) => {
      const read = readModelAnswer(
        ["half a lemon"],
        { rows: [{ quantity, ingredient: "lemon" }] },
        [EMPTY_ROW],
      );

      expect(read.ok && read.value.kept).toEqual([]);
    },
  );

  it.each(["a few", "1-2", "-1", "100001"])(
    "keeps the built-in scan when the quantity is not a number it can save: %s",
    (quantity) => {
      const read = readModelAnswer(
        ["a few 1-2 -1 100001 lemons"],
        { rows: [{ quantity, ingredient: "lemons" }] },
        [EMPTY_ROW],
      );

      expect(read.ok && read.value.kept).toEqual([0]);
    },
  );
});

// #181: a line in another language comes back in English, so its words
// cannot be found in it; the model says which rows it translated.
describe("readModelAnswer, translating", () => {
  const ITALIAN = ["2 cucchiai di olio d'oliva"];

  it("takes a translated row whose words are not in its line, and says so", () => {
    const read = readModelAnswer(
      ITALIAN,
      {
        rows: [
          {
            quantity: "2",
            unit: "tbsp",
            ingredient: "olive oil",
            translated: true,
          },
        ],
      },
      [EMPTY_ROW],
    );

    expect(read).toEqual({
      ok: true,
      value: {
        rows: [
          {
            ...EMPTY_ROW,
            quantity: "2",
            unit: "tbsp",
            ingredient: "olive oil",
          },
        ],
        kept: [],
        missed: [],
        translated: [0],
      },
    });
  });

  it("still checks a translated row's quantity", () => {
    const read = readModelAnswer(
      ITALIAN,
      {
        rows: [{ quantity: "due", ingredient: "olive oil", translated: true }],
      },
      [EMPTY_ROW],
    );

    expect(read.ok && read.value).toEqual({
      rows: [EMPTY_ROW],
      kept: [0],
      missed: [],
      translated: [],
    });
  });

  it("checks the words of a row not marked as translated", () => {
    const read = readModelAnswer(
      ITALIAN,
      { rows: [{ quantity: "2", ingredient: "olive oil", translated: false }] },
      [EMPTY_ROW],
    );

    expect(read.ok && read.value.kept).toEqual([0]);
  });

  // Seen by hand (#182): a small model said it translated Italian lines and
  // gave them back in Italian.
  it("does not count a row as translated when its words are the line's", () => {
    const read = readModelAnswer(
      ["3 uova piccole"],
      {
        rows: [
          {
            quantity: "3",
            ingredient: "uova",
            note: "piccole",
            translated: true,
          },
        ],
      },
      [EMPTY_ROW],
    );

    expect(read.ok && read.value).toMatchObject({ kept: [], translated: [] });
  });

  it("refuses a translated flag that is not true or false", () => {
    expect(
      readModelAnswer(
        ITALIAN,
        { rows: [{ ingredient: "oil", translated: "yes" }] },
        [EMPTY_ROW],
      ).ok,
    ).toBe(false);
  });
});

// Seen by hand (#182): a small local model merged two of nine lines, and
// the whole answer was lost. Lines go numbered, and each row says its line.
// Seen by hand (#182): "3 uova piccole" came back with the unit "uova".
describe("readModelAnswer, with the user's units", () => {
  const knownUnit = (unit: string) => ["g", "tbsp", "ml"].includes(unit);

  it("keeps the built-in scan of a row whose unit is not one of the user's", () => {
    const read = readModelAnswer(
      ["3 uova piccole"],
      { rows: [{ quantity: "3", unit: "uova", ingredient: "piccole" }] },
      [EMPTY_ROW],
      knownUnit,
    );

    expect(read.ok && read.value.kept).toEqual([0]);
  });

  it("takes a row whose unit is one of the user's, or has none", () => {
    const read = readModelAnswer(LINES, GOOD, BUILT_IN, knownUnit);

    expect(read.ok && read.value.kept).toEqual([]);
  });

  it("checks a translated row's unit too", () => {
    const read = readModelAnswer(
      ["2 cucchiai di olio d'oliva"],
      {
        rows: [
          {
            quantity: "2",
            unit: "spoons",
            ingredient: "olive oil",
            translated: true,
          },
        ],
      },
      [EMPTY_ROW],
      knownUnit,
    );

    expect(read.ok && read.value.kept).toEqual([0]);
  });
});

describe("readModelAnswer, by line number", () => {
  const numberedRow = (line: number, row: object) => ({ line, ...row });

  it("matches rows to lines by their numbers", () => {
    const read = readModelAnswer(
      LINES,
      { rows: [numberedRow(2, GOOD.rows[1]!), numberedRow(1, GOOD.rows[0]!)] },
      BUILT_IN,
    );

    expect(read.ok && read.value.rows).toEqual(GOOD.rows);
  });

  it("keeps the built-in scan of a line the model gave no row", () => {
    const read = readModelAnswer(
      LINES,
      { rows: [numberedRow(1, GOOD.rows[0]!)] },
      BUILT_IN,
    );

    expect(read).toEqual({
      ok: true,
      value: {
        rows: [GOOD.rows[0], BUILT_IN[1]],
        kept: [],
        missed: [1],
        translated: [],
      },
    });
  });

  it("ignores a row for a line not sent, and a second row for a line", () => {
    const read = readModelAnswer(
      LINES,
      {
        rows: [
          numberedRow(1, GOOD.rows[0]!),
          numberedRow(1, { ingredient: "olive" }),
          numberedRow(2, GOOD.rows[1]!),
          numberedRow(3, { ingredient: "salt" }),
        ],
      },
      BUILT_IN,
    );

    expect(read.ok && read.value.rows).toEqual(GOOD.rows);
  });

  it("refuses rows that match none of the lines", () => {
    expect(
      readModelAnswer(
        LINES,
        { rows: [numberedRow(7, GOOD.rows[0]!)] },
        BUILT_IN,
      ),
    ).toEqual({
      ok: false,
      error: "The model's rows matched none of the lines.",
    });
  });

  it.each([["1"], [1.5], [null]])(
    "refuses a line number that is not a whole number: %j",
    (line) => {
      expect(
        readModelAnswer(LINES, { rows: [{ ...GOOD.rows[0], line }] }, BUILT_IN)
          .ok,
      ).toBe(false);
    },
  );
});

describe("numbered", () => {
  it("numbers the lines from 1, as the model is sent them", () => {
    expect(numbered(LINES)).toEqual([
      { line: 1, text: "2 tbsp olive oil" },
      { line: 2, text: "1 onion, finely chopped" },
    ]);
  });
});

describe("MODEL_INSTRUCTION", () => {
  it("asks for a line in another language in English", () => {
    expect(MODEL_INSTRUCTION).toMatch(
      /not in English, translate it into English/,
    );
  });

  it("shows a line in another language translated, as an example", () => {
    expect(MODEL_INSTRUCTION).toMatch(/For example/);
    expect(MODEL_INSTRUCTION).toContain('"ingredient":"onions"');
  });

  it("asks for exactly one row per line, never two lines merged", () => {
    expect(MODEL_INSTRUCTION).toMatch(/exactly one row for each line/);
    expect(MODEL_INSTRUCTION).toMatch(/Never merge two lines/);
  });
});

describe("rowsSchema", () => {
  it("asks for every field of a row, and its line's number", () => {
    expect(rowsSchema(2).properties.rows.items.required).toEqual([
      "line",
      ...Object.keys(EMPTY_ROW),
      "translated",
    ]);
  });

  it("asks for exactly one row per line", () => {
    expect(rowsSchema(9).properties.rows).toMatchObject({
      minItems: 9,
      maxItems: 9,
    });
  });
});

describe("lineOf", () => {
  it("says a row again as one line, in the order a recipe writes it", () => {
    expect(
      lineOf({
        quantity: "2",
        unit: "tbsp",
        ingredient: "butter",
        substitute: "ghee",
        preparation: "melted",
        note: "to serve",
        rest: "plus extra",
      }),
    ).toBe("2 tbsp butter or ghee, melted, to serve plus extra");
  });

  it("leaves out what is empty", () => {
    expect(lineOf({ ...EMPTY_ROW, ingredient: "salt" })).toBe("salt");
    expect(lineOf({ ...EMPTY_ROW, rest: "a handful of herbs" })).toBe(
      "a handful of herbs",
    );
    expect(lineOf(EMPTY_ROW)).toBe("");
  });
});

describe("describeSplit", () => {
  it.each([
    [2, [], [], "The model split 2 lines."],
    [1, [], [], "The model split 1 line."],
    [
      2,
      [],
      [0, 1],
      "The model split 2 lines, and translated 2 of them into English.",
    ],
    [
      2,
      [1],
      [],
      "The model split 2 lines; 1 of its rows did not match its line, so that row is as it was.",
    ],
    [
      3,
      [0, 2],
      [1],
      "The model split 3 lines, and translated 1 of them into English; 2 of its rows did not match their lines, so those rows are as they were.",
    ],
  ])("says what it did with %i lines", (lines, kept, translated, said) => {
    expect(
      describeSplit(lines, { rows: [], kept, missed: [], translated }),
    ).toBe(said);
  });

  it("says how many lines the model gave no row", () => {
    expect(
      describeSplit(9, { rows: [], kept: [0], missed: [3], translated: [] }),
    ).toBe(
      "The model split 9 lines; 1 of its rows did not match its line, so that row is as it was; it gave no row for 1 line, so that row is as it was.",
    );
    expect(
      describeSplit(9, { rows: [], kept: [], missed: [3, 4], translated: [] }),
    ).toBe(
      "The model split 9 lines; it gave no row for 2 lines, so those rows are as they were.",
    );
  });
});
