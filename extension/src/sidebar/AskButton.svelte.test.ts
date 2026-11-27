import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AskButton from "./AskButton.svelte";

const OTHERS = [
  { id: "2", name: "Haiku" },
  { id: "3", name: "Qwen3 on llama.cpp" },
];

function renderAsk(
  options: {
    others?: readonly { id: string; name: string }[];
    current?: string;
    holdMs?: number;
  } = {},
) {
  const onAsk = vi.fn<(setupId?: string) => void>();
  render(AskButton, {
    label: "Ask the model about group 1",
    others: options.others ?? OTHERS,
    disabled: false,
    onAsk,
    ...(options.current === undefined ? {} : { current: options.current }),
    ...(options.holdMs === undefined ? {} : { holdMs: options.holdMs }),
  });
  return { onAsk, button: screen.getByRole("button", { name: /^Ask/ }) };
}

/** Press and hold for this long, then let go, as a mouse would. */
async function hold(button: HTMLElement, ms: number) {
  await fireEvent.pointerDown(button, { button: 0 });
  await vi.advanceTimersByTimeAsync(ms);
  await fireEvent.pointerUp(button, { button: 0 });
  await fireEvent.click(button);
}

describe("Ask the model, and another model once (#183)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("asks the default model on a click", async () => {
    const { onAsk, button } = renderAsk();
    await fireEvent.click(button);

    expect(onAsk).toHaveBeenCalledExactlyOnceWith(undefined);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("says how to reach the others", () => {
    const { button } = renderAsk();

    expect(button).toHaveAttribute("aria-haspopup", "menu");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button.title).toMatch(/hold/i);
  });

  it("opens a menu of the other models after a 1 second hold, and asks none", async () => {
    const { onAsk, button } = renderAsk();
    await hold(button, 1000);

    const menu = screen.getByRole("menu", { name: "Ask another model" });
    expect(
      [...menu.querySelectorAll("[role=menuitem]")].map(
        (item) => item.textContent,
      ),
    ).toEqual(["Haiku", "Qwen3 on llama.cpp"]);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(onAsk).not.toHaveBeenCalled();
  });

  // Asked for in the #205 PR: the hold is the user's to set.
  it("waits as long as it is told to before opening the menu", async () => {
    const { onAsk, button } = renderAsk({ holdMs: 2500 });
    await hold(button, 2000);

    expect(screen.queryByRole("menu")).toBeNull();
    expect(onAsk).toHaveBeenCalledExactlyOnceWith(undefined);

    await hold(button, 2500);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(button.title).toMatch(/Hold for 2.5 seconds/);
    // The honey fills the button over the same time.
    expect(button.style.getPropertyValue("--hold")).toBe("2500ms");
  });

  it("says how long to hold", () => {
    expect(renderAsk().button.title).toMatch(/^Hold for 1 second,/);
  });

  // Asked for in the #205 PR: the default, faded, as a reminder.
  it("shows the default model first in the menu, faded and not to be picked", async () => {
    const { onAsk, button } = renderAsk({ current: "Sonnet" });
    await fireEvent.keyDown(button, { key: "Enter", shiftKey: true });

    const current = screen.getByRole("menuitem", { name: "Sonnet (default)" });
    expect(current).toBeDisabled();
    expect(
      [...screen.getByRole("menu").querySelectorAll("[role=menuitem]")].map(
        (item) => item.textContent,
      ),
    ).toEqual(["Sonnet (default)", "Haiku", "Qwen3 on llama.cpp"]);
    expect(screen.getByRole("menuitem", { name: "Haiku" })).toHaveFocus();

    await fireEvent.click(current);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("skips the default when moving with the arrow keys", async () => {
    renderAsk({ current: "Sonnet" });
    await fireEvent.contextMenu(screen.getByRole("button"));
    const haiku = screen.getByRole("menuitem", { name: "Haiku" });
    const qwen = screen.getByRole("menuitem", { name: "Qwen3 on llama.cpp" });

    await fireEvent.keyDown(haiku, { key: "ArrowUp" });
    expect(qwen).toHaveFocus();
    await fireEvent.keyDown(qwen, { key: "ArrowDown" });
    expect(haiku).toHaveFocus();
  });

  it("asks the default when let go sooner", async () => {
    const { onAsk, button } = renderAsk();
    await hold(button, 900);

    expect(screen.queryByRole("menu")).toBeNull();
    expect(onAsk).toHaveBeenCalledExactlyOnceWith(undefined);
  });

  it("forgets a hold the pointer slid off", async () => {
    const { button } = renderAsk();
    await fireEvent.pointerDown(button, { button: 0 });
    await fireEvent.pointerLeave(button);
    await vi.advanceTimersByTimeAsync(1000);

    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("asks the one picked, once, and gives the focus back", async () => {
    const { onAsk, button } = renderAsk();
    await hold(button, 1000);
    await fireEvent.click(screen.getByRole("menuitem", { name: "Haiku" }));

    expect(onAsk).toHaveBeenCalledExactlyOnceWith("2");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("opens the same menu on Shift+Enter, on the first model", async () => {
    const { onAsk, button } = renderAsk();
    await fireEvent.keyDown(button, { key: "Enter", shiftKey: true });

    expect(screen.getByRole("menuitem", { name: "Haiku" })).toHaveFocus();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("opens it on a right-click or the context-menu key, instead of the browser's", async () => {
    const { button } = renderAsk();
    const shown = await fireEvent.contextMenu(button);

    expect(shown).toBe(false);
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("moves between the models with the arrow keys", async () => {
    renderAsk();
    await fireEvent.contextMenu(screen.getByRole("button"));
    const haiku = screen.getByRole("menuitem", { name: "Haiku" });
    const qwen = screen.getByRole("menuitem", { name: "Qwen3 on llama.cpp" });

    await fireEvent.keyDown(haiku, { key: "ArrowDown" });
    expect(qwen).toHaveFocus();
    await fireEvent.keyDown(qwen, { key: "ArrowDown" });
    expect(haiku).toHaveFocus();
    await fireEvent.keyDown(haiku, { key: "ArrowUp" });
    expect(qwen).toHaveFocus();
  });

  it("shuts on Escape, asking nothing", async () => {
    const { onAsk, button } = renderAsk();
    await fireEvent.contextMenu(button);
    await fireEvent.keyDown(screen.getByRole("menuitem", { name: "Haiku" }), {
      key: "Escape",
    });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("shuts on a press anywhere else", async () => {
    const { button } = renderAsk();
    await fireEvent.contextMenu(button);
    await fireEvent.pointerDown(document.body);

    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("is a plain button when there is no other model", async () => {
    const { onAsk, button } = renderAsk({ others: [] });
    await hold(button, 1000);
    const shown = await fireEvent.contextMenu(button);
    await fireEvent.keyDown(button, { key: "Enter", shiftKey: true });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(shown).toBe(true);
    expect(button).not.toHaveAttribute("aria-haspopup");
    expect(button.title).toBe("");
    expect(onAsk).toHaveBeenCalledExactlyOnceWith(undefined);
  });
});
