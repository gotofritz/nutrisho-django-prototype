import { err, ok, type Result } from "./result";
import {
  EMPTY_ROW,
  QUANTITY_LIMIT,
  type IngredientRow,
} from "./ingredient-line";

/**
 * A model's split of ingredient lines, checked before it is shown (plan 012,
 * M13, #181). The model is sent the lines numbered, and asked for
 * `{"rows": [...]}`, a row per line, each with its line's number and its
 * fields as strings. An answer of another shape is refused whole; a row
 * with a field its line does not hold, or a line given no row, keeps the
 * built-in scan, so one invented word or two lines merged (#182) does not
 * cost the whole group. Rows with no numbers are taken in order, and must
 * then be one per line. A line
 * in another language comes back in English, marked `translated`: its words
 * cannot be found in its line, so only its quantity is checked.
 */
export interface ModelRows {
  readonly rows: readonly IngredientRow[];
  /** The rows that kept their built-in scan, by index. */
  readonly kept: readonly number[];
  /** The lines the model gave no row, which kept theirs too, by index. */
  readonly missed: readonly number[];
  /** The rows the model translated into English, by index. */
  readonly translated: readonly number[];
}

/** A row as the model answers it: the fields, and whether it translated them. */
interface AnsweredRow {
  readonly row: IngredientRow;
  readonly translated: boolean;
  /** The number of its line, from 1, when the model gave one. */
  readonly line?: number;
}

const FIELDS = Object.keys(EMPTY_ROW) as (keyof IngredientRow)[];

const SHAPE = "The model's answer was not in the shape asked for.";

/** A quantity as the server keeps it: a plain decimal, below the limit. */
const NUMBER = /^\d+(\.\d+)?$/;

function plain(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

/** The row, if it is an object of string fields; a missing one is empty. */
function rowOf(value: unknown): AnsweredRow | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const fields = value as Partial<
    Record<keyof IngredientRow | "translated" | "line", unknown>
  >;
  const translated = fields.translated ?? false;
  if (typeof translated !== "boolean") return undefined;
  const { line } = fields;
  if (line !== undefined && !Number.isInteger(line)) return undefined;
  const row: Record<string, string> = {};
  for (const field of FIELDS) {
    const text = fields[field] ?? "";
    if (typeof text !== "string") return undefined;
    row[field] = text.trim();
  }
  return {
    row: row as unknown as IngredientRow,
    translated,
    ...(line === undefined ? {} : { line: line as number }),
  };
}

/** The lines as the model is sent them: numbered from 1. */
export function numbered(
  lines: readonly string[],
): { line: number; text: string }[] {
  return lines.map((text, index) => ({ line: index + 1, text }));
}

/**
 * What becomes of a row: taken as answered, taken as a translation, or kept
 * as the built-in scan had it. Its quantity must be a number it can save,
 * and its unit one of the user's. Its words must be its line's, unless the
 * model translated it; a row that says so but copied its line's words was
 * not translated (#182), so is not counted as one.
 */
function verdict(
  line: string,
  { row, translated }: AnsweredRow,
  knownUnit: (unit: string) => boolean,
): "taken" | "translated" | "kept" {
  const { quantity, ...words } = row;
  if (
    quantity !== "" &&
    !(NUMBER.test(quantity) && Number(quantity) < QUANTITY_LIMIT)
  ) {
    return "kept";
  }
  if (row.unit !== "" && !knownUnit(row.unit)) return "kept";
  const haystack = plain(line);
  const copied = Object.values(words).every(
    (text) => text === "" || haystack.includes(plain(text)),
  );
  if (copied) return "taken";
  return translated ? "translated" : "kept";
}

export function readModelAnswer(
  lines: readonly string[],
  answer: unknown,
  builtIn: readonly IngredientRow[],
  /** Whether a unit is one of the user's; any is, while the lists are not loaded. */
  knownUnit: (unit: string) => boolean = () => true,
): Result<ModelRows, string> {
  const listed =
    typeof answer === "object" && answer !== null
      ? (answer as { rows?: unknown }).rows
      : undefined;
  if (!Array.isArray(listed)) return err(SHAPE);
  const answered = listed.map(rowOf);
  if (answered.includes(undefined)) return err(SHAPE);
  const rows = answered as AnsweredRow[];
  const byNumber = rows.some((row) => row.line !== undefined);
  if (byNumber && rows.some((row) => row.line === undefined)) return err(SHAPE);
  if (!byNumber && rows.length !== lines.length) {
    return err(
      `The model answered ${rows.length} rows for ${lines.length} lines.`,
    );
  }
  // Each line's row: by its number, the first given for it; or in order.
  const rowFor = (index: number): AnsweredRow | undefined =>
    byNumber ? rows.find((row) => row.line === index + 1) : rows[index];
  if (lines.every((_, index) => rowFor(index) === undefined)) {
    return err("The model's rows matched none of the lines.");
  }

  const kept: number[] = [];
  const missed: number[] = [];
  const translated: number[] = [];
  const checked = lines.map((line, index) => {
    const row = rowFor(index);
    const judged = row === undefined ? "missed" : verdict(line, row, knownUnit);
    if (row !== undefined && judged !== "kept" && judged !== "missed") {
      if (judged === "translated") translated.push(index);
      return row.row;
    }
    (judged === "missed" ? missed : kept).push(index);
    return builtIn[index] ?? EMPTY_ROW;
  });
  return ok({ rows: checked, kept, missed, translated });
}

/**
 * The answer's shape, as a JSON schema, for a provider that can hold a model
 * to one: exactly as many rows as lines, which llama.cpp's grammar keeps to.
 */
export function rowsSchema(lines: number) {
  return {
    type: "object",
    properties: {
      rows: {
        type: "array",
        minItems: lines,
        maxItems: lines,
        items: {
          type: "object",
          properties: {
            line: { type: "integer" },
            ...Object.fromEntries(
              FIELDS.map((field) => [field, { type: "string" }]),
            ),
            translated: { type: "boolean" },
          },
          required: ["line", ...FIELDS, "translated"],
        },
      },
    },
    required: ["rows"],
  } as const;
}

/** Two lines in Italian and one in English, as the model should answer them. */
const EXAMPLE_LINES = numbered([
  "2 cipolle grandi, tritate",
  "400 g di pomodori pelati",
  "1 tbsp olive oil, plus extra to serve",
]);

const EXAMPLE_ROWS = [
  {
    line: 1,
    quantity: "2",
    unit: "",
    ingredient: "onions",
    substitute: "",
    preparation: "chopped",
    note: "large",
    rest: "",
    translated: true,
  },
  {
    line: 2,
    quantity: "400",
    unit: "g",
    ingredient: "peeled tomatoes",
    substitute: "",
    preparation: "",
    note: "",
    rest: "",
    translated: true,
  },
  {
    line: 3,
    quantity: "1",
    unit: "tbsp",
    ingredient: "olive oil",
    substitute: "",
    preparation: "",
    note: "plus extra to serve",
    rest: "",
    translated: false,
  },
];

/** What the model is told, before the lines; nothing about the user or the page. */
export const MODEL_INSTRUCTION = [
  "You split recipe ingredient lines into fields.",
  'The user sends a JSON array of numbered lines: [{"line": 1, "text": "..."}, ...]. Answer with JSON only: {"rows": [...]}, exactly one row for each line, in the same order, each with the number of its line.',
  "Never merge two lines into one row, nor split one line into two rows, even when they name the same ingredient.",
  "Each row has the number line, the string fields quantity, unit, ingredient, substitute, preparation, note and rest, an absent field being an empty string, and the boolean translated.",
  "If a line is not in English, translate it into English, using the words an English recipe would, and set translated to true.",
  "Otherwise set translated to false and copy words from the line exactly; do not correct, pluralise or add words.",
  'quantity is a plain decimal number such as 2, 0.5 or 400, or empty; write "half" or "½" as 0.5.',
  "unit is a measure such as g, tbsp or cup, never the ingredient itself: in 3 eggs the unit is empty. ingredient is what is used, in the words of the line or their English. substitute is an alternative named with or. preparation is what is done to it, such as finely chopped. note is anything else worth keeping, such as to serve.",
  "rest holds words of the line that fit no field.",
  `For example, these lines: ${JSON.stringify(EXAMPLE_LINES)}`,
  `become: ${JSON.stringify({ rows: EXAMPLE_ROWS })}`,
].join("\n");

/**
 * A row said again as one line, which is what the model is sent: the clip's
 * own text is not kept, and the row may have been edited since.
 */
export function lineOf(row: IngredientRow): string {
  const head = [row.quantity, row.unit, row.ingredient]
    .filter((part) => part !== "")
    .join(" ");
  const named = row.substitute === "" ? head : `${head} or ${row.substitute}`;
  const parts = [named, row.preparation, row.note].filter(
    (part) => part !== "",
  );
  return [parts.join(", "), row.rest].filter((part) => part !== "").join(" ");
}

/** What the model did to a group, for the sidebar to say, by its name (#183). */
export function describeSplit(
  lines: number,
  split: ModelRows,
  who = "The model",
): string {
  const { kept, missed, translated } = split;
  let said = `${who} split ${lines} ${lines === 1 ? "line" : "lines"}`;
  if (translated.length > 0) {
    said += `, and translated ${translated.length} of them into English`;
  }
  if (kept.length === 1) {
    said += "; 1 of its rows did not match its line, so that row is as it was";
  } else if (kept.length > 1) {
    said += `; ${kept.length} of its rows did not match their lines, so those rows are as they were`;
  }
  if (missed.length === 1) {
    said += "; it gave no row for 1 line, so that row is as it was";
  } else if (missed.length > 1) {
    said += `; it gave no row for ${missed.length} lines, so those rows are as they were`;
  }
  return `${said}.`;
}
