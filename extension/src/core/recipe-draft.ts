import { scanLine, type IngredientRow } from "./ingredient-line";
import type { Vocabulary } from "./vocabulary";

/**
 * The recipe being clipped (plan 012, M7): pure data, and the rules for
 * changing it. The sidebar edits it; the server receives it as a Nutrisho
 * document (`server/docs/features/import-export.md`).
 *
 * Every field is text as typed, servings and quantities included, so what
 * the user sees is what is stored; `checkDraft` says what stops a save.
 */
export interface RecipeDraft {
  /** A version 7 UUID, made when the draft starts, so a save sent twice makes one recipe (D8). */
  readonly id: string;
  readonly name: string;
  readonly blurb: string;
  /** Blank means the server's default, 1. */
  readonly servings: string;
  /** The page it was clipped from. */
  readonly source: string;
  /** A dotted path through the cuisine tree; picked in M8. */
  readonly cuisine: string;
  /** Picked in M8. */
  readonly tags: readonly string[];
  readonly groups: readonly IngredientGroup[];
  readonly steps: readonly string[];
  /** ISO 8601. */
  readonly startedAt: string;
}

/** Ingredient rows under one heading, which may be blank (D7). */
export interface IngredientGroup {
  readonly name: string;
  readonly rows: readonly IngredientRow[];
}

/** Where captured text can go (D3). */
export type DraftTarget = "name" | "blurb" | "group" | "steps";

export interface DraftIssue {
  /** `name`, `servings`, or `groups.<index>.rows.<index>.<field>`. */
  readonly field: string;
  readonly message: string;
}

/** Recipe.servings is a PositiveSmallIntegerField. */
const MAX_SERVINGS = 32_767;
/** IngredientInRecipe.quantity holds 7 digits, 2 of them decimals. */
const QUANTITY = /^\d{1,5}([.,]\d{1,2})?$/;

export function startDraft({
  id,
  title,
  url,
  now,
}: {
  id: string;
  title: string;
  url: string;
  now: string;
}): RecipeDraft {
  return {
    id,
    name: title.trim(),
    blurb: "",
    servings: "",
    source: url,
    cuisine: "",
    tags: [],
    groups: [],
    steps: [],
    startedAt: now,
  };
}

/** Enough of a shape check to tell a draft from whatever else is stored. */
export function isRecipeDraft(value: unknown): value is RecipeDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<Record<keyof RecipeDraft, unknown>>;
  const text = (field: unknown) => typeof field === "string";

  return (
    [draft.id, draft.name, draft.blurb, draft.servings, draft.source]
      .concat([draft.cuisine, draft.startedAt])
      .every(text) &&
    Array.isArray(draft.tags) &&
    Array.isArray(draft.groups) &&
    Array.isArray(draft.steps)
  );
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

function oneLine(text: string): string {
  return lines(text).join(" ");
}

/**
 * One ingredient group from text: a row for each line, scanned against the
 * lists. When nothing in the first line is known and more lines follow, it is
 * taken for the group's name (`For the syrup:`), without its colon.
 */
export function groupFrom(
  text: string,
  vocabulary: Vocabulary,
): IngredientGroup {
  const rows = lines(text).map((line) => scanLine(line, vocabulary));
  const [first, ...rest] = rows;
  if (first !== undefined && rest.length > 0 && first.ingredient === "") {
    return { name: first.rest.replace(/:$/, "").trim(), rows: rest };
  }
  return { name: "", rows };
}

function joined(before: string, after: string, separator: string): string {
  return before === "" ? after : `${before}${separator}${after}`;
}

function send(
  draft: RecipeDraft,
  target: DraftTarget,
  text: string,
  vocabulary: Vocabulary,
  keep: boolean,
): RecipeDraft {
  if (text.trim() === "") return draft;

  switch (target) {
    case "name":
      return {
        ...draft,
        name: keep ? joined(draft.name, oneLine(text), " ") : oneLine(text),
      };
    case "blurb":
      return {
        ...draft,
        blurb: keep ? joined(draft.blurb, text.trim(), "\n\n") : text.trim(),
      };
    case "group": {
      const group = groupFrom(text, vocabulary);
      return { ...draft, groups: keep ? [...draft.groups, group] : [group] };
    }
    case "steps": {
      const steps = lines(text);
      return { ...draft, steps: keep ? [...draft.steps, ...steps] : steps };
    }
  }
}

/** *Add to*: the text goes after what the target holds. */
export function addTo(
  draft: RecipeDraft,
  target: DraftTarget,
  text: string,
  vocabulary: Vocabulary,
): RecipeDraft {
  return send(draft, target, text, vocabulary, true);
}

/** *Replace*: the text takes the place of what the target holds. */
export function replace(
  draft: RecipeDraft,
  target: DraftTarget,
  text: string,
  vocabulary: Vocabulary,
): RecipeDraft {
  return send(draft, target, text, vocabulary, false);
}

export function updateRow(
  draft: RecipeDraft,
  groupIndex: number,
  rowIndex: number,
  patch: Partial<IngredientRow>,
): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex
        ? {
            ...group,
            rows: group.rows.map((row, place) =>
              place === rowIndex ? { ...row, ...patch } : row,
            ),
          }
        : group,
    ),
  };
}

export function updateGroupName(
  draft: RecipeDraft,
  groupIndex: number,
  name: string,
): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex ? { ...group, name } : group,
    ),
  };
}

export function updateStep(
  draft: RecipeDraft,
  index: number,
  text: string,
): RecipeDraft {
  return {
    ...draft,
    steps: draft.steps.map((step, at) => (at === index ? text : step)),
  };
}

export function withDetails(
  draft: RecipeDraft,
  patch: Partial<Pick<RecipeDraft, "name" | "blurb" | "servings" | "source">>,
): RecipeDraft {
  return { ...draft, ...patch };
}

function quantityIssue(quantity: string): boolean {
  const written = quantity.trim();
  return written !== "" && !QUANTITY.test(written);
}

function servingsIssue(servings: string): boolean {
  const written = servings.trim();
  if (written === "") return false;
  return (
    !/^\d+$/.test(written) ||
    Number(written) < 1 ||
    Number(written) > MAX_SERVINGS
  );
}

/**
 * What stops a save, in the order the fields are shown. The server checks
 * everything again; these are the mistakes worth catching before a round
 * trip, each named by the field it is in.
 */
export function checkDraft(draft: RecipeDraft): DraftIssue[] {
  const issues: DraftIssue[] = [];
  if (draft.name.trim() === "") {
    issues.push({ field: "name", message: "The recipe needs a name." });
  }
  if (servingsIssue(draft.servings)) {
    issues.push({
      field: "servings",
      message: `Servings must be a whole number from 1 to ${MAX_SERVINGS}.`,
    });
  }
  draft.groups.forEach((group, groupIndex) => {
    // With one group a row's number is enough; with more, the group is named.
    const of =
      draft.groups.length > 1
        ? ` of ${group.name.trim() || `group ${groupIndex + 1}`}`
        : "";
    group.rows.forEach((row, index) => {
      const at = `groups.${groupIndex}.rows.${index}`;
      if (quantityIssue(row.quantity)) {
        issues.push({
          field: `${at}.quantity`,
          message: `The quantity in row ${index + 1}${of} is not a number the recipe can hold, such as 2, 1.5 or 0.25.`,
        });
      }
      if (row.ingredient.trim() === "") {
        issues.push({
          field: `${at}.ingredient`,
          message: `Row ${index + 1}${of} has no ingredient.`,
        });
      }
    });
  });
  return issues;
}

/** `POST` here; the id makes a second save of one draft answer with the first's recipe. */
export function savePath(draft: RecipeDraft): string {
  return `/recipes/api/recipes/?id=${draft.id}`;
}

function documentRow(row: IngredientRow) {
  const quantity = row.quantity.trim().replace(",", ".");
  return {
    ingredient: row.ingredient.trim(),
    substitute: row.substitute.trim(),
    quantity: quantity === "" ? null : quantity,
    unit: row.unit.trim(),
    legacy_unit: "",
    preparation: row.preparation.trim(),
    // The scan's leftovers are kept, never dropped (M7).
    note: [row.note.trim(), row.rest.trim()].filter(Boolean).join(" "),
  };
}

/** The draft as a Nutrisho document of one recipe, as the save endpoint reads it. */
export function toDocument(draft: RecipeDraft): unknown {
  const servings = draft.servings.trim();
  return {
    format: "nutrisho",
    version: 1,
    recipes: [
      {
        recipe_name: draft.name.trim(),
        short_description: draft.blurb.trim(),
        ...(servings === "" ? {} : { servings: Number(servings) }),
        source_instance: draft.source,
        cuisine: draft.cuisine,
        tags: [...draft.tags],
        steps: draft.steps.map((step) => ({ step_title: "", step_text: step })),
        ingredient_groups: draft.groups
          .filter((group) => group.rows.length > 0 || group.name.trim() !== "")
          .map((group) => ({
            group_name: group.name.trim(),
            items: group.rows.map(documentRow),
          })),
      },
    ],
  };
}
