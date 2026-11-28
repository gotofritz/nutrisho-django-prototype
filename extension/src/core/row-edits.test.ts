import { describe, expect, it } from "vitest";

import { EMPTY_ROW } from "./ingredient-line";
import { fromRest, hasNoteFlag, withNoteFlag } from "./row-edits";

// #202: *to taste* and *optional* are ticked on a row, and kept in its note.
describe("hasNoteFlag", () => {
  it.each([
    ["to taste", true],
    ["Salt, to taste", true],
    ["TO TASTE, or more", true],
    ["tasted", false],
    ["", false],
  ])("finds `to taste` in %j: %s", (note, found) => {
    expect(hasNoteFlag(note, "to taste")).toBe(found);
  });

  it("finds `optional` as a word of its own", () => {
    expect(hasNoteFlag("optional", "optional")).toBe(true);
    expect(hasNoteFlag("for garnish (optional)", "optional")).toBe(true);
    expect(hasNoteFlag("optionally", "optional")).toBe(false);
  });
});

describe("withNoteFlag", () => {
  it("adds the flag to an empty note, or after what is there", () => {
    expect(withNoteFlag("", "to taste", true)).toBe("to taste");
    expect(withNoteFlag("for garnish", "optional", true)).toBe(
      "for garnish, optional",
    );
  });

  it("adds nothing when the note has it already", () => {
    expect(withNoteFlag("Salt, to taste", "to taste", true)).toBe(
      "Salt, to taste",
    );
  });

  it("takes the flag out, with the comma that joined it", () => {
    expect(withNoteFlag("to taste", "to taste", false)).toBe("");
    expect(withNoteFlag("for garnish, optional", "optional", false)).toBe(
      "for garnish",
    );
    expect(withNoteFlag("optional, for garnish", "optional", false)).toBe(
      "for garnish",
    );
    expect(withNoteFlag("to taste, optional", "to taste", false)).toBe(
      "optional",
    );
  });

  it("leaves a note without the flag as it is", () => {
    expect(withNoteFlag("for garnish", "optional", false)).toBe("for garnish");
  });
});

// #202: Rest's Prep, Sub and Note copy its text to that field.
describe("fromRest", () => {
  const ROW = { ...EMPTY_ROW, ingredient: "basil", rest: "a handful of, torn" };

  it("fills an empty field with the text", () => {
    expect(fromRest(ROW, "preparation", "torn")).toEqual({
      preparation: "torn",
    });
  });

  it("adds to the preparation or the note after a comma", () => {
    expect(fromRest({ ...ROW, note: "to taste" }, "note", "a handful")).toEqual(
      { note: "to taste, a handful" },
    );
    expect(
      fromRest({ ...ROW, preparation: "washed" }, "preparation", "torn"),
    ).toEqual({ preparation: "washed, torn" });
  });

  it("replaces the substitute, which is one ingredient", () => {
    expect(
      fromRest({ ...ROW, substitute: "mint" }, "substitute", "parsley"),
    ).toEqual({ substitute: "parsley" });
  });

  it("takes the text tidied, and nothing when there is none", () => {
    expect(fromRest(ROW, "note", "  , a handful of,  ")).toEqual({
      note: "a handful of",
    });
    expect(fromRest(ROW, "note", " ")).toEqual({});
  });
});
