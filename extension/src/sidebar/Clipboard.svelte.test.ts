import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import Clipboard from "./Clipboard.svelte";

function renderClipboard(text = "2 lemons\n200 g sugar") {
  const onSend = vi.fn();
  render(Clipboard, { text, onSend });
  return { onSend, box: screen.getByRole("textbox", { name: "Clipboard" }) };
}

// Plan 012, D3: captured text lands here, and from here is added to the
// name, blurb, ingredients or steps, or replaces what they hold.
describe("the clipboard", () => {
  it("holds the clipped text", () => {
    const { box } = renderClipboard();

    expect(box).toHaveValue("2 lemons\n200 g sugar");
  });

  it.each([
    ["Add to name", "name", "add"],
    ["Replace name", "name", "replace"],
    ["Add to blurb", "blurb", "add"],
    ["Replace blurb", "blurb", "replace"],
    ["Add to ingredient groups", "group", "add"],
    ["Replace ingredient groups", "group", "replace"],
    ["Add to steps", "steps", "add"],
    ["Replace steps", "steps", "replace"],
  ])("sends all of it with %s", async (button, target, mode) => {
    const { onSend } = renderClipboard();

    await fireEvent.click(screen.getByRole("button", { name: button }));

    expect(onSend).toHaveBeenCalledWith(target, mode, "2 lemons\n200 g sugar");
  });

  it("sends only the part selected, when part is", async () => {
    const { onSend, box } = renderClipboard();
    (box as HTMLTextAreaElement).setSelectionRange(0, 8);

    await fireEvent.click(
      screen.getByRole("button", { name: "Add to ingredient groups" }),
    );

    expect(onSend).toHaveBeenCalledWith("group", "add", "2 lemons");
  });

  // Typed or pasted text is treated the same as clipped text (D3).
  it("sends what was typed into it", async () => {
    const { onSend, box } = renderClipboard("");

    await fireEvent.input(box, { target: { value: "Serves 4" } });
    await fireEvent.click(screen.getByRole("button", { name: "Add to blurb" }));

    expect(onSend).toHaveBeenCalledWith("blurb", "add", "Serves 4");
  });

  it("sends nothing while it is empty", () => {
    renderClipboard("  ");

    expect(screen.getByRole("button", { name: "Add to steps" })).toBeDisabled();
  });
});
