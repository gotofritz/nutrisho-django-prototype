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
    });
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
  ])("refuses %s", (_, value) => {
    expect(isClipping(value)).toBe(false);
  });
});
