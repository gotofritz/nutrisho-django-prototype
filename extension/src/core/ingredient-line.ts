import type { Term, Vocabulary } from "./vocabulary";

/**
 * One ingredient row, with the site's fields (plan 012, D6) plus `rest`: the
 * words the scan was not sure of, in order. Every field is text, as typed;
 * the quantity is checked when the draft is saved.
 */
export interface IngredientRow {
  readonly quantity: string;
  readonly unit: string;
  readonly ingredient: string;
  readonly substitute: string;
  readonly preparation: string;
  readonly note: string;
  readonly rest: string;
}

export const EMPTY_ROW: IngredientRow = {
  quantity: "",
  unit: "",
  ingredient: "",
  substitute: "",
  preparation: "",
  note: "",
  rest: "",
};

/** IngredientInRecipe.quantity holds 7 digits, 2 of them decimals. */
const QUANTITY_LIMIT = 100_000;

const VULGAR: Readonly<Record<string, readonly [number, number]>> = {
  "½": [1, 2],
  "⅓": [1, 3],
  "⅔": [2, 3],
  "¼": [1, 4],
  "¾": [3, 4],
  "⅕": [1, 5],
  "⅖": [2, 5],
  "⅗": [3, 5],
  "⅘": [4, 5],
  "⅙": [1, 6],
  "⅚": [5, 6],
  "⅛": [1, 8],
  "⅜": [3, 8],
  "⅝": [5, 8],
  "⅞": [7, 8],
};

/** A word as the lists are looked up: lower case, without the punctuation around it. */
function normalise(word: string): string {
  return word.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
}

function phrase(words: readonly string[]): string {
  return words.map(normalise).join(" ");
}

/** Every spelling of every term, to the term's canonical name. */
function index(terms: readonly Term[]): {
  names: Map<string, string>;
  longest: number;
} {
  const names = new Map<string, string>();
  let longest = 0;
  for (const term of terms) {
    for (const spelling of [term.name, ...term.spellings]) {
      const words = spelling.trim().split(/\s+/);
      const key = phrase(words);
      if (key !== "" && !names.has(key)) names.set(key, term.name);
      longest = Math.max(longest, words.length);
    }
  }
  return { names, longest };
}

interface Found {
  readonly start: number;
  readonly end: number;
  readonly name: string;
}

/** The longest run of words that is a name in `terms`; the first, on a tie. */
function longestName(
  words: readonly string[],
  terms: readonly Term[],
): Found | undefined {
  const { names, longest } = index(terms);
  for (let length = Math.min(longest, words.length); length > 0; length -= 1) {
    for (let start = 0; start + length <= words.length; start += 1) {
      const name = names.get(phrase(words.slice(start, start + length)));
      if (name !== undefined) return { start, end: start + length, name };
    }
  }
  return undefined;
}

/** A name in `terms` that ends just before `end`, the longest first. */
function nameEndingAt(
  words: readonly string[],
  end: number,
  terms: readonly Term[],
): Found | undefined {
  const { names, longest } = index(terms);
  for (let length = Math.min(longest, end); length > 0; length -= 1) {
    const name = names.get(phrase(words.slice(end - length, end)));
    if (name !== undefined) return { start: end - length, end, name };
  }
  return undefined;
}

type Fraction = readonly [numerator: number, denominator: number];

/** One written amount: `2`, `1.5`, `1,5`, `1/2`, `½` or `1½`. */
function amount(word: string): Fraction | undefined {
  if (/^\d+$/.test(word)) return [Number(word), 1];
  const decimal = /^(\d+)[.,](\d+)$/.exec(word);
  if (decimal) {
    const denominator = 10 ** decimal[2]!.length;
    return [Number(decimal[1]) * denominator + Number(decimal[2]), denominator];
  }
  const fraction = /^(\d+)\/(\d+)$/.exec(word);
  if (fraction && Number(fraction[2]) > 0) {
    return [Number(fraction[1]), Number(fraction[2])];
  }
  const vulgar = /^(\d*)(\D)$/u.exec(word);
  const part = vulgar ? VULGAR[vulgar[2]!] : undefined;
  if (vulgar && part) {
    const whole = vulgar[1] === "" ? 0 : Number(vulgar[1]);
    return [whole * part[1] + part[0], part[1]];
  }
  return undefined;
}

/** As the server stores it: rounded half up to cents, without trailing zeros. */
function decimalText([numerator, denominator]: Fraction): string | undefined {
  const cents = Math.floor((200 * numerator + denominator) / (2 * denominator));
  if (cents >= QUANTITY_LIMIT * 100) return undefined;
  const whole = Math.floor(cents / 100);
  const fraction = String(cents % 100)
    .padStart(2, "0")
    .replace(/0+$/, "");
  return fraction === "" ? String(whole) : `${whole}.${fraction}`;
}

interface Quantity {
  readonly start: number;
  readonly end: number;
  readonly text: string;
}

/** The amount written just before `end`, with a whole number in front of a fraction. */
function quantityEndingAt(
  words: readonly string[],
  end: number,
): Quantity | undefined {
  const last = end > 0 ? amount(words[end - 1]!) : undefined;
  if (last === undefined) return undefined;

  let value: Fraction = last;
  let start = end - 1;
  // `1 1/2` and `1 ½` are one amount: a fraction alone, after a whole number.
  const fractionAlone = /^(\d+\/\d+|\D)$/u.test(words[start]!);
  if (fractionAlone && start > 0 && /^\d+$/.test(words[start - 1]!)) {
    value = [Number(words[start - 1]) * last[1] + last[0], last[1]];
    start -= 1;
  }
  const text = decimalText(value);
  return text === undefined ? undefined : { start, end, text };
}

const GLUED = new RegExp(
  `^(\\d+(?:[.,]\\d+)?|\\d+\\/\\d+|\\d*[${Object.keys(VULGAR).join("")}])(\\p{L}[\\p{L}.]*)$`,
  "u",
);

/** A scanned word, and the written word it came from. */
interface Piece {
  readonly text: string;
  readonly from: number;
}

/** `600ml` is two words, an amount and a unit, when the letters are a unit in the list. */
function unglued(written: readonly string[], units: readonly Term[]): Piece[] {
  const { names } = index(units);
  return written.flatMap((word, from) => {
    const glued = GLUED.exec(word);
    return glued && names.has(normalise(glued[2]!))
      ? [
          { text: glued[1]!, from },
          { text: glued[2]!, from },
        ]
      : [{ text: word, from }];
  });
}

/** The longest name in `terms` that starts at `start` and ends by `limit`. */
function nameStartingAt(
  words: readonly string[],
  start: number,
  limit: number,
  terms: readonly Term[],
): Found | undefined {
  const { names, longest } = index(terms);
  for (let length = Math.min(longest, limit - start); length > 0; length -= 1) {
    const name = names.get(phrase(words.slice(start, start + length)));
    if (name !== undefined) return { start, end: start + length, name };
  }
  return undefined;
}

/** An amount with a unit straight after it, the nearest to `limit` that ends by it. */
function amountWithUnit(
  words: readonly string[],
  limit: number,
  units: readonly Term[],
): { quantity: Quantity; unit: Found } | undefined {
  for (let end = limit - 1; end > 0; end -= 1) {
    const unit = nameStartingAt(words, end, limit, units);
    const quantity = unit && quantityEndingAt(words, end);
    if (unit && quantity) return { quantity, unit };
  }
  return undefined;
}

/** With no better candidate, the amount nearest before `limit` (`2 large eggs`). */
function nearestQuantity(
  words: readonly string[],
  limit: number,
): Quantity | undefined {
  for (let end = limit - 1; end > 0; end -= 1) {
    const quantity = quantityEndingAt(words, end);
    if (quantity !== undefined) return quantity;
  }
  return undefined;
}

/** What a written word ends with that rest keeps when the word is taken. */
const KEPT_PUNCTUATION = /[,;:]+$/;

/**
 * The words the scan did not take, as written: an amount against its unit
 * stays one word, and the comma after a word it took stays too.
 */
function restOf(
  written: readonly string[],
  pieces: readonly Piece[],
  used: ReadonlySet<number>,
): string {
  let rest = "";
  pieces.forEach((piece, at) => {
    const last = pieces[at + 1]?.from !== piece.from;
    if (used.has(at)) {
      const kept = last ? KEPT_PUNCTUATION.exec(written[piece.from]!) : null;
      if (kept && rest !== "") rest += kept[0];
      return;
    }
    const sameWord = at > 0 && pieces[at - 1]!.from === piece.from;
    const joined = sameWord && !used.has(at - 1);
    rest += rest === "" || joined ? piece.text : ` ${piece.text}`;
  });
  return rest;
}

/**
 * Scan one line into a row (plan 012, M7). A field is filled only when the
 * scan is sure, and every other word stays, in order, in `rest`:
 *
 * - the ingredient is the longest name from the loaded list the line holds,
 *   in its canonical spelling;
 * - the unit is a name from the loaded list directly before the ingredient,
 *   or straight after an amount before it (`190g plain flour`);
 * - the quantity is a number directly before the unit, or before the
 *   ingredient when there is no unit; failing that, the nearest number
 *   before them (`2 large eggs`).
 */
export function scanLine(line: string, vocabulary: Vocabulary): IngredientRow {
  const written = line.trim().split(/\s+/).filter(Boolean);
  const pieces = unglued(written, vocabulary.units);
  const words = pieces.map((piece) => piece.text);
  const used = new Set<number>();
  const take = (start: number, end: number) => {
    for (let at = start; at < end; at += 1) used.add(at);
  };

  const ingredient = longestName(words, vocabulary.ingredients);
  let unit: Found | undefined;
  let quantity: Quantity | undefined;
  if (ingredient !== undefined) {
    take(ingredient.start, ingredient.end);
    unit = nameEndingAt(words, ingredient.start, vocabulary.units);
    quantity = quantityEndingAt(words, (unit ?? ingredient).start);
    const apart =
      quantity === undefined
        ? amountWithUnit(words, ingredient.start, vocabulary.units)
        : undefined;
    if (apart !== undefined) ({ quantity, unit } = apart);
    quantity ??= nearestQuantity(words, (unit ?? ingredient).start);
    if (unit !== undefined) take(unit.start, unit.end);
    if (quantity !== undefined) take(quantity.start, quantity.end);
  }

  return {
    ...EMPTY_ROW,
    quantity: quantity?.text ?? "",
    unit: unit?.name ?? "",
    ingredient: ingredient?.name ?? "",
    rest: restOf(written, pieces, used),
  };
}
