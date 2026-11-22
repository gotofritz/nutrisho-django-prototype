import { describe, expect, it } from "vitest";

import { fitText } from "./fit-text.dom";

/** jsdom lays nothing out, so the text's height is given. */
function box(textHeight: number): HTMLTextAreaElement {
  const area = document.createElement("textarea");
  Object.defineProperty(area, "scrollHeight", {
    configurable: true,
    get: () => textHeight,
  });
  document.body.append(area);
  return area;
}

// A step clipped from a page is often long; its box grows to show all of it.
describe("fitText", () => {
  it("makes the box as tall as its text", () => {
    const area = box(120);

    fitText(area, "A long step.");

    expect(area.style.height).toBe("120px");
  });

  it("follows the text as it is typed", () => {
    const area = box(40);
    fitText(area, "Short.");

    Object.defineProperty(area, "scrollHeight", { get: () => 90 });
    area.dispatchEvent(new Event("input"));

    expect(area.style.height).toBe("90px");
  });

  it("follows the text when it changes from outside", () => {
    const area = box(40);
    const action = fitText(area, "Short.");

    Object.defineProperty(area, "scrollHeight", { get: () => 200 });
    action.update("A step clipped from the page, much longer.");

    expect(area.style.height).toBe("200px");
  });

  it("stops following once removed", () => {
    const area = box(40);
    const action = fitText(area, "Short.");
    action.destroy();

    Object.defineProperty(area, "scrollHeight", { get: () => 90 });
    area.dispatchEvent(new Event("input"));

    expect(area.style.height).toBe("40px");
  });
});
