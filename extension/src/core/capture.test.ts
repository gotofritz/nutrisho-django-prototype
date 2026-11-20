import { describe, expect, it } from "vitest";

import { SELECTION_CAP, capText, warn } from "./capture";

describe("capText", () => {
  it("leaves text shorter than the cap alone", () => {
    expect(capText("Heat the oven.", SELECTION_CAP)).toEqual({
      text: "Heat the oven.",
      truncated: false,
    });
  });

  it("leaves text exactly at the cap alone", () => {
    const text = "x".repeat(SELECTION_CAP);

    expect(capText(text, SELECTION_CAP)).toEqual({ text, truncated: false });
  });

  // Select-all on a long article is megabytes, and the cap has to bite before
  // any of it crosses a message boundary.
  it("truncates at the cap and says so", () => {
    const capped = capText("y".repeat(SELECTION_CAP + 1), SELECTION_CAP);

    expect(capped.text).toHaveLength(SELECTION_CAP);
    expect(capped.truncated).toBe(true);
  });
});

describe("warn", () => {
  it("pairs a kind with the message the user is shown", () => {
    expect(warn("shadow-dom", "the selection is inside a shadow root")).toEqual(
      {
        kind: "shadow-dom",
        message: "the selection is inside a shadow root",
      },
    );
  });
});
