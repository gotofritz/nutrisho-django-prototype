import { EMPTY_ROW, scanLine, type IngredientRow } from "./ingredient-line";
import type { Vocabulary } from "./vocabulary";

/** One step of the method, under an optional title, as on the site. */
export interface Step {
  readonly title: string;
  readonly text: string;
}

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
  /** Where the recipe came from: the page it was clipped from, until edited. */
  readonly source: string;
  /**
   * The page it was clipped from, which clips from that page are matched on;
   * not shown, so editing the source does not part a draft from its page.
   * Absent from drafts stored before it was kept, which use the source.
   */
  readonly clippedFrom?: string;
  /** A dotted path through the cuisine tree, or a bare name, as typed. */
  readonly cuisine: string;
  /**
   * The tags field's text split at its commas, untrimmed, so joining them
   * gives back what was typed; `tagNames` gives the tags themselves.
   */
  readonly tags: readonly string[];
  readonly groups: readonly IngredientGroup[];
  /** The one ingredient group shown open, by index; none when absent. */
  readonly openGroup?: number;
  readonly steps: readonly Step[];
  /** ISO 8601. */
  readonly startedAt: string;
}

/** Ingredient rows under one heading, which may be blank (D7). */
export interface IngredientGroup {
  readonly name: string;
  readonly rows: readonly IngredientRow[];
}

/** Where captured text can go (D3). */
/**
 * Where text goes: `group` starts a new ingredient group, `ingredient` adds
 * rows to the open one (or starts one when none is open).
 */
export type DraftTarget = "name" | "blurb" | "group" | "ingredient" | "steps";

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
    clippedFrom: url,
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
    (draft.openGroup === undefined || typeof draft.openGroup === "number") &&
    Array.isArray(draft.steps) &&
    draft.steps.every(
      (step: unknown) =>
        typeof step === "object" &&
        step !== null &&
        text((step as Step).title) &&
        text((step as Step).text),
    )
  );
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

/**
 * A line carries on the line before when it starts with a comma (`, cubed`)
 * or a bracket (`(about 2 tsp)`), or the line before ends with a comma.
 */
function continued(split: readonly string[]): string[] {
  return split.reduce<string[]>((joined, line) => {
    const before = joined.length - 1;
    if (before < 0) joined.push(line);
    else if (/^[,;]/.test(line)) joined[before] += line;
    else if (/^\(/.test(line) || /,$/.test(joined[before]!)) {
      joined[before] += ` ${line}`;
    } else joined.push(line);
    return joined;
  }, []);
}

function oneLine(text: string): string {
  return lines(text).join(" ");
}

/** The lines of a block of ingredients, a line carried on joined to its own. */
function ingredientLines(text: string): string[] {
  return continued(lines(text).filter((line) => /[\p{L}\p{N}]/u.test(line)));
}

/** Ingredient lines as rows, with no group name taken from them. */
function rowsFrom(text: string, vocabulary: Vocabulary): IngredientRow[] {
  return ingredientLines(text).map((line) => scanLine(line, vocabulary));
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
  const split = ingredientLines(text);
  const rows = split.map((line) => scanLine(line, vocabulary));
  const [first, ...rest] = rows;
  const [firstLine = ""] = split;
  const named =
    first !== undefined &&
    first.quantity === "" &&
    (first.ingredient === "" || /^for\b|:$/i.test(firstLine));
  if (named && rest.length > 0) {
    return { name: firstLine.replace(/:$/, "").trim(), rows: rest };
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
      const groups = keep ? [...draft.groups, group] : [group];
      return { ...draft, groups, openGroup: groups.length - 1 };
    }
    case "ingredient": {
      const open = draft.openGroup;
      const group = open === undefined ? undefined : draft.groups[open];
      if (open === undefined || group === undefined) {
        return send(draft, "group", text, vocabulary, true);
      }
      const rows = rowsFrom(text, vocabulary);
      return {
        ...draft,
        groups: draft.groups.map((held, at) =>
          at === open
            ? { ...held, rows: keep ? [...held.rows, ...rows] : rows }
            : held,
        ),
      };
    }
    case "steps": {
      const steps = lines(text).map((line) => ({ title: "", text: line }));
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
  patch: Partial<Step>,
): RecipeDraft {
  return {
    ...draft,
    steps: draft.steps.map((step, at) =>
      at === index ? { ...step, ...patch } : step,
    ),
  };
}

/** An empty step after the one at `after`, or at the end, to type into. */
export function addStep(
  draft: RecipeDraft,
  after = draft.steps.length - 1,
): RecipeDraft {
  const steps = [...draft.steps];
  steps.splice(after + 1, 0, { title: "", text: "" });
  return { ...draft, steps };
}

/** One place up (-1) or down (1); the first stays put going up, the last going down. */
export function moveStep(
  draft: RecipeDraft,
  index: number,
  by: -1 | 1,
): RecipeDraft {
  const to = index + by;
  if (to < 0 || to >= draft.steps.length) return draft;
  const steps = [...draft.steps];
  [steps[index], steps[to]] = [steps[to]!, steps[index]!];
  return { ...draft, steps };
}

/**
 * One place up (-1) or down (1). A group's first row going up joins the end
 * of the group before, and its last going down the start of the group after,
 * which opens so the row stays in sight.
 */
export function moveRow(
  draft: RecipeDraft,
  groupIndex: number,
  rowIndex: number,
  by: -1 | 1,
): RecipeDraft {
  const rows = draft.groups[groupIndex]?.rows ?? [];
  const row = rows[rowIndex];
  if (row === undefined) return draft;
  const to = rowIndex + by;
  if (to >= 0 && to < rows.length) {
    const moved = [...rows];
    [moved[rowIndex], moved[to]] = [moved[to]!, row];
    return withRows(draft, groupIndex, moved);
  }
  const target = groupIndex + by;
  const into = draft.groups[target];
  if (into === undefined) return draft;
  const left = withRows(
    draft,
    groupIndex,
    rows.filter((_, at) => at !== rowIndex),
  );
  const joined = by < 0 ? [...into.rows, row] : [row, ...into.rows];
  return { ...withRows(left, target, joined), openGroup: target };
}

function withRows(
  draft: RecipeDraft,
  groupIndex: number,
  rows: readonly IngredientRow[],
): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex ? { ...group, rows } : group,
    ),
  };
}

/** A row read as a heading: its parts in the order they usually come, less a closing colon. */
function headingOf(row: IngredientRow): string {
  return [
    row.quantity,
    row.unit,
    row.rest,
    row.ingredient,
    row.substitute,
    row.preparation,
    row.note,
  ]
    .map((part) => part.trim())
    .filter((part) => part !== "")
    .join(" ")
    .replace(/\s*:$/, "");
}

/**
 * A heading caught inside a group (D7): the row becomes the name of a new
 * group, after this one, holding the rows below it, and that group opens. The
 * first row instead becomes this group's own name.
 */
export function splitGroupAt(
  draft: RecipeDraft,
  groupIndex: number,
  rowIndex: number,
): RecipeDraft {
  const group = draft.groups[groupIndex];
  const row = group?.rows[rowIndex];
  if (group === undefined || row === undefined) return draft;
  const name = headingOf(row);
  const below = group.rows.slice(rowIndex + 1);
  if (rowIndex === 0) {
    return {
      ...draft,
      groups: draft.groups.map((at, index) =>
        index === groupIndex ? { name, rows: below } : at,
      ),
    };
  }
  const groups = [...draft.groups];
  groups.splice(
    groupIndex,
    1,
    { ...group, rows: group.rows.slice(0, rowIndex) },
    { name, rows: below },
  );
  return { ...draft, groups, openGroup: groupIndex + 1 };
}

/** Takes one step out. */
export function removeStep(draft: RecipeDraft, index: number): RecipeDraft {
  return { ...draft, steps: draft.steps.filter((_, at) => at !== index) };
}

/** Takes one group out, rows and all. */
export function removeGroup(
  draft: RecipeDraft,
  groupIndex: number,
): RecipeDraft {
  const open = draft.openGroup;
  const groups = draft.groups.filter((_, at) => at !== groupIndex);
  const openGroup =
    open === undefined || open === groupIndex
      ? undefined
      : open > groupIndex
        ? open - 1
        : open;
  return { ...draft, groups, openGroup };
}

/** Open one ingredient group, closing the others; or close them all. */
export function withOpenGroup(
  draft: RecipeDraft,
  groupIndex: number | undefined,
): RecipeDraft {
  return { ...draft, openGroup: groupIndex };
}

/** Takes one row out of a group; the group stays, even when it is left empty. */
export function removeRow(
  draft: RecipeDraft,
  groupIndex: number,
  rowIndex: number,
): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex
        ? { ...group, rows: group.rows.filter((_, row) => row !== rowIndex) }
        : group,
    ),
  };
}

export function withDetails(
  draft: RecipeDraft,
  patch: Partial<
    Pick<RecipeDraft, "name" | "blurb" | "servings" | "source" | "cuisine">
  >,
): RecipeDraft {
  return { ...draft, ...patch };
}

/** The tags as typed: comma-separated, as on the site. */
export function withTags(draft: RecipeDraft, text: string): RecipeDraft {
  return { ...draft, tags: text.split(",") };
}

/** The tags field's text, exactly as typed. */
export function tagsText(draft: RecipeDraft): string {
  return draft.tags.join(",");
}

/** Each tag once, trimmed, blanks left out; the first spelling of a name wins. */
export function tagNames(draft: RecipeDraft): string[] {
  const seen = new Set<string>();
  return draft.tags
    .map((tag) => tag.trim())
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (tag === "" || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
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
/** Whether a row goes into the clip: only one that names an ingredient. */
function clipped(row: IngredientRow): boolean {
  return row.ingredient.trim() !== "";
}

/** An empty group, with one empty row to type into. */
export function addGroup(draft: RecipeDraft): RecipeDraft {
  return {
    ...draft,
    groups: [...draft.groups, { name: "", rows: [{ ...EMPTY_ROW }] }],
    openGroup: draft.groups.length,
  };
}

/** An empty row at the end of one group. */
export function addRow(draft: RecipeDraft, groupIndex: number): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex
        ? { ...group, rows: [...group.rows, EMPTY_ROW] }
        : group,
    ),
  };
}

/** Characters as the server counts them: code points, after trimming. */
function length(text: string): number {
  return [...text.trim()].length;
}

/**
 * Text too long for its field (D12), in the order the fields are shown, by
 * the server's own `limits`; a field with no limit loaded is not checked.
 */
export function lengthIssues(
  draft: RecipeDraft,
  limits: Readonly<Record<string, number>>,
): DraftIssue[] {
  const issues: DraftIssue[] = [];
  function check(field: string, key: string, what: string, text: string) {
    const limit = limits[key];
    const over = limit === undefined ? 0 : length(text) - limit;
    if (over > 0) {
      const characters = over === 1 ? "character" : "characters";
      issues.push({
        field,
        message: `${what} is ${over} ${characters} too long: it can have ${limit}.`,
      });
    }
  }
  const label = (field: string) => labelOf(draft, field);
  check("name", "recipe_name", label("name"), draft.name);
  check("blurb", "short_description", label("blurb"), draft.blurb);
  check("source", "source_instance", label("source"), draft.source);
  check("cuisine", "cuisine", label("cuisine"), draft.cuisine);
  for (const tag of tagNames(draft)) {
    check("tags", "tags", `The tag “${tag}”`, tag);
  }
  draft.groups.forEach((group, groupIndex) => {
    const at = `groups.${groupIndex}`;
    check(`${at}.name`, "group_name", label(`${at}.name`), group.name);
    group.rows.forEach((row, index) => {
      for (const field of ROW_TEXT) {
        const path = `${at}.rows.${index}.${field}`;
        check(path, field, label(path), row[field]);
      }
    });
  });
  draft.steps.forEach((step, index) => {
    const at = `steps.${index}`;
    check(`${at}.title`, "step_title", label(`${at}.title`), step.title);
    check(`${at}.text`, "step_text", label(`${at}.text`), step.text);
  });
  return issues;
}

/** A row's fields that are sent as text, by the server's names for them. */
const ROW_TEXT = [
  "unit",
  "ingredient",
  "substitute",
  "preparation",
  "note",
] as const;

export function checkDraft(
  draft: RecipeDraft,
  limits: Readonly<Record<string, number>> = {},
): DraftIssue[] {
  const issues: DraftIssue[] = lengthIssues(draft, limits);
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
      // A row with no ingredient is left out of the clip (#182), so nothing
      // in it can stop one.
      if (!clipped(row)) return;
      const at = `groups.${groupIndex}.rows.${index}`;
      if (quantityIssue(row.quantity)) {
        issues.push({
          field: `${at}.quantity`,
          message: `The quantity in row ${index + 1}${of} is not a number the recipe can hold, such as 2, 1.5 or 0.25.`,
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
    // Rest is the row's scratch pad, and is never sent.
    note: row.note.trim(),
  };
}

/** The recipe's own fields, by the document's name for each. */
const DOCUMENT_FIELDS: Readonly<Record<string, string>> = {
  recipe_name: "name",
  short_description: "blurb",
  servings: "servings",
  source_instance: "source",
  cuisine: "cuisine",
};

/** A row's fields, by the document's names, which are the draft's too. */
const ROW_FIELDS = new Set<string>(["quantity", ...ROW_TEXT]);

/**
 * How a field of the draft is named to the user: `name`, `steps.2.title`,
 * `groups.0.rows.1.unit`. A row names its group when there is more than one.
 */
function labelOf(draft: RecipeDraft, field: string): string {
  const step = /^steps\.(\d+)\.(title|text)$/.exec(field);
  if (step !== null) {
    const n = Number(step[1]) + 1;
    return step[2] === "title" ? `The title of step ${n}` : `Step ${n}`;
  }
  const group = /^groups\.(\d+)\.name$/.exec(field);
  if (group !== null) return `The name of group ${Number(group[1]) + 1}`;
  const row = /^groups\.(\d+)\.rows\.(\d+)\.(\w+)$/.exec(field);
  if (row !== null) {
    const groupIndex = Number(row[1]);
    const name =
      draft.groups[groupIndex]?.name.trim() || `group ${groupIndex + 1}`;
    const of = draft.groups.length > 1 ? ` of ${name}` : "";
    return `The ${row[3]} in row ${Number(row[2]) + 1}${of}`;
  }
  return `The ${field}`;
}

/** The indices of `items` that `keep` keeps, in order: the document's index → the draft's. */
function kept<T>(items: readonly T[], keep: (item: T) => boolean): number[] {
  return items.flatMap((item, index) => (keep(item) ? [index] : []));
}

/** The draft's field at a path of the document `toDocument` made, or undefined. */
function fieldAtPath(draft: RecipeDraft, path: string): string | undefined {
  const own = DOCUMENT_FIELDS[path];
  if (own !== undefined) return own;
  if (/^tags(\[\d+\])?$/.test(path)) return "tags";
  const step = /^steps\[(\d+)\]\.step_(title|text)$/.exec(path);
  if (step !== null) {
    const index = kept(
      draft.steps,
      (s) => s.title.trim() !== "" || s.text.trim() !== "",
    )[Number(step[1])];
    return index === undefined ? undefined : `steps.${index}.${step[2]}`;
  }
  const group =
    /^ingredient_groups\[(\d+)\]\.(?:group_name|items\[(\d+)\]\.(\w+))$/.exec(
      path,
    );
  if (group === null) return undefined;
  const groupIndex = kept(draft.groups, (g) => g.rows.some(clipped))[
    Number(group[1])
  ];
  if (groupIndex === undefined) return undefined;
  if (group[2] === undefined) return `groups.${groupIndex}.name`;
  const rowIndex = kept(draft.groups[groupIndex]!.rows, clipped)[
    Number(group[2])
  ];
  if (rowIndex === undefined || !ROW_FIELDS.has(group[3]!)) return undefined;
  return `groups.${groupIndex}.rows.${rowIndex}.${group[3]}`;
}

/**
 * A save the server refused, read against the draft that was sent (plan 012,
 * M11). The server names the field by its path in the document, as in
 * `document.recipes[0].steps[2].step_title must be at most 128 characters.`;
 * this is that field of the draft, and the message in the editor's words.
 * Undefined when the message names no field of the draft.
 */
export function explainRefusal(
  draft: RecipeDraft,
  message: string,
): DraftIssue | undefined {
  const named = /^document\.recipes\[0\]\.(\S+) (.*)$/.exec(message);
  if (named === null) return undefined;
  const [, path, rest] = named;
  const field = fieldAtPath(draft, path!);
  if (field === undefined) return undefined;
  const tag = /^tags\[(\d+)\]$/.exec(path!);
  const tagName = tag === null ? undefined : tagNames(draft)[Number(tag[1])];
  const label =
    tagName === undefined ? labelOf(draft, field) : `The tag “${tagName}”`;
  return { field, message: `${label} ${rest}` };
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
        cuisine: draft.cuisine.trim(),
        tags: tagNames(draft),
        // An empty step is left out, wherever it is.
        steps: draft.steps
          .map((step) => ({
            step_title: step.title.trim(),
            step_text: step.text.trim(),
          }))
          .filter((step) => step.step_title !== "" || step.step_text !== ""),
        // Rows with no ingredient are left out, then groups left with none.
        ingredient_groups: draft.groups
          .map((group) => ({
            group_name: group.name.trim(),
            items: group.rows.filter(clipped).map(documentRow),
          }))
          .filter((group) => group.items.length > 0),
      },
    ],
  };
}

/** One group with other rows: the model's, or those before them (M13). */
export function withGroupRows(
  draft: RecipeDraft,
  groupIndex: number,
  rows: readonly IngredientRow[],
): RecipeDraft {
  return {
    ...draft,
    groups: draft.groups.map((group, at) =>
      at === groupIndex ? { ...group, rows } : group,
    ),
  };
}

/** The draft with its steps replaced, as the model rewrote them (#181). */
export function withSteps(
  draft: RecipeDraft,
  steps: readonly Step[],
): RecipeDraft {
  return { ...draft, steps };
}
