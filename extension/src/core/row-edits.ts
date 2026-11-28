import type { IngredientRow } from "./ingredient-line";

/**
 * Edits on one ingredient row that the sidebar offers as buttons and boxes
 * (#202). Pure text work, so the editor only wires them up.
 */

/** What a row's two boxes tick, both kept in its note. */
export type NoteFlag = "to taste" | "optional";

function flagPattern(flag: NoteFlag): RegExp {
  return new RegExp(`(?<![\\p{L}\\p{N}])${flag}(?![\\p{L}\\p{N}])`, "giu");
}

/** Whether the note says it, as words of their own, in any case. */
export function hasNoteFlag(note: string, flag: NoteFlag): boolean {
  return flagPattern(flag).test(note);
}

/** Commas and spaces left at the ends, or doubled, once a part is taken out. */
function tidyNote(note: string): string {
  return note
    .replace(/\(\s*\)/g, "")
    .replace(/\s*,(\s*,)+/g, ",")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,]+|[\s,]+$/g, "");
}

/** The note with the flag after what is there, or without it. */
export function withNoteFlag(
  note: string,
  flag: NoteFlag,
  on: boolean,
): string {
  if (on) {
    if (hasNoteFlag(note, flag)) return note;
    return note.trim() === "" ? flag : `${note.trim()}, ${flag}`;
  }
  return hasNoteFlag(note, flag)
    ? tidyNote(note.replace(flagPattern(flag), ""))
    : note;
}

/** The fields Rest's buttons copy to. */
export type RestTarget = "preparation" | "substitute" | "note";

/**
 * Rest's text, or the part of it picked, copied to a field: after a comma
 * in the preparation or the note, in place of the substitute, which names
 * one ingredient.
 */
export function fromRest(
  row: IngredientRow,
  field: RestTarget,
  text: string,
): Partial<IngredientRow> {
  const copied = text.replace(/^[\s,;]+|[\s,;]+$/g, "");
  if (copied === "") return {};
  const there = row[field].trim();
  return {
    [field]:
      field === "substitute" || there === "" ? copied : `${there}, ${copied}`,
  };
}
