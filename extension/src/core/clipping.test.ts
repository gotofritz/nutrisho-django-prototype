import { describe, expect, it } from "vitest";

import type { PageCapture } from "./capture";
import { clippingFrom, isClipping } from "./clipping";

const CAPTURE: PageCapture = {
  text: "2 aubergines\n1 tbsp olive oil",
  title: "Melanzane — Example",
  url: "https://example.test/melanzane",
  warnings: [{ kind: "selection-truncated", message: "cut" }],
};

describe("clippingFrom", () => {
  it("keeps the text, the page it came from and its blind spots", () => {
    const clipping = clippingFrom(CAPTURE, new Date("2026-11-20T09:30:00Z"));

    expect(clipping).toEqual({
      text: "2 aubergines\n1 tbsp olive oil",
      title: "Melanzane — Example",
      url: "https://example.test/melanzane",
      clippedAt: "2026-11-20T09:30:00.000Z",
      warnings: [{ kind: "selection-truncated", message: "cut" }],
      target: "group",
    });
  });

  // The right-click submenu names where the text goes; the shortcut and the
  // toolbar button send it to a new ingredient group (M12: no clipboard).
  it("keeps where the text was sent", () => {
    expect(clippingFrom(CAPTURE, new Date(), "steps").target).toBe("steps");
  });

  it("is a plain value that survives extension storage", () => {
    const clipping = clippingFrom(CAPTURE, new Date("2026-11-20T09:30:00Z"));

    expect(structuredClone(clipping)).toEqual(clipping);
  });
});

describe("isClipping", () => {
  it("knows a clipping", () => {
    expect(isClipping(clippingFrom(CAPTURE, new Date()))).toBe(true);
  });

  // Kept from before M12, when a clipping could go to the clipboard only.
  it("is not a clipping sent to the clipboard, which is gone", () => {
    expect(
      isClipping({ ...clippingFrom(CAPTURE, new Date()), target: "clipboard" }),
    ).toBe(false);
  });

  // From M7 to M12 a clipping kept the selection's markup too.
  it("knows a clipping stored while the markup was kept", () => {
    expect(
      isClipping({
        ...clippingFrom(CAPTURE, new Date()),
        html: "<p>2 aubergines</p>",
      }),
    ).toBe(true);
  });

  it.each([
    ["nothing", undefined],
    ["a string", "basil"],
    [
      "an object with no text",
      { title: "", url: "", clippedAt: "", warnings: [] },
    ],
    [
      "warnings that are not a list",
      { text: "", title: "", url: "", clippedAt: "", warnings: "none" },
    ],
    [
      "a target it does not know",
      {
        text: "",
        title: "",
        url: "",
        clippedAt: "",
        warnings: [],
        target: "ingredients",
      },
    ],
  ])("refuses %s", (_, value) => {
    expect(isClipping(value)).toBe(false);
  });
});
