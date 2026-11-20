import type { NutrishoError } from "./ports/types";
import { err, ok, type Result } from "./result";

/**
 * What the user can name in a recipe, as `GET /recipes/api/vocabulary/`
 * answers (plan 012, M4): loaded each time the sidebar opens (D4), and checked
 * against in the browser from M8.
 */
export interface Term {
  /** The canonical spelling, which a saved recipe uses. */
  readonly name: string;
  /** Every other spelling the server resolves to this one: plurals, aliases. */
  readonly spellings: readonly string[];
}

export interface Vocabulary {
  /** Whose lists these are: the key's user. */
  readonly user: string;
  readonly ingredients: readonly Term[];
  readonly units: readonly Term[];
  /** Dotted paths through the cuisine tree, such as `med.italy`. */
  readonly cuisines: readonly string[];
  readonly tags: readonly string[];
  /** The longest text each field takes, by the server's own names (D12). */
  readonly limits: Readonly<Record<string, number>>;
}

export const EMPTY_VOCABULARY: Vocabulary = {
  user: "",
  ingredients: [],
  units: [],
  cuisines: [],
  tags: [],
  limits: {},
};

const isString = (value: unknown): value is string => typeof value === "string";

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isTermList(value: unknown): value is Term[] {
  return (
    Array.isArray(value) &&
    value.every(
      (term: unknown) =>
        typeof term === "object" &&
        term !== null &&
        isString((term as Term).name) &&
        isStringList((term as Term).spellings),
    )
  );
}

function isLimits(value: unknown): value is Record<string, number> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((limit) => typeof limit === "number")
  );
}

/**
 * The reply's body, checked. A reply that is not the shape the server's
 * example shows is refused whole, rather than half-used. A section this
 * version does not know is ignored: a later kind of data is a new section,
 * and an older clipper must still read the rest.
 */
export function parseVocabulary(
  body: unknown,
): Result<Vocabulary, NutrishoError> {
  const reply =
    typeof body === "object" && body !== null && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : undefined;
  const { user, ingredients, units, cuisines, tags, limits } = reply ?? {};

  if (
    reply === undefined ||
    !isString(user) ||
    !isTermList(ingredients) ||
    !isTermList(units) ||
    !isStringList(cuisines) ||
    !isStringList(tags) ||
    !isLimits(limits)
  ) {
    return err({
      kind: "malformed-response",
      message: "the server's lists are not in the shape this clipper reads",
    });
  }
  return ok({ user, ingredients, units, cuisines, tags, limits });
}
