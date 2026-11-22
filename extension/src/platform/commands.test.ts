import { browser } from "wxt/browser";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createCommands } from "./commands";

type CommandListener = (command: string, tab?: { id?: number }) => void;

let listeners: CommandListener[];

beforeEach(() => {
  listeners = [];
  browser.commands = {
    onCommand: {
      addListener: vi.fn((listener: CommandListener) => {
        listeners.push(listener);
      }),
      removeListener: vi.fn((listener: CommandListener) => {
        listeners = listeners.filter((it) => it !== listener);
      }),
    },
  } as never;
});

describe("commands", () => {
  it("delivers a shortcut as its name and the tab it fired in", () => {
    const onCommand = vi.fn();
    createCommands().onCommand(onCommand);

    listeners.forEach((listener) => listener("clip-recipe", { id: 7 }));

    expect(onCommand).toHaveBeenCalledWith({
      command: "clip-recipe",
      tabId: 7,
    });
  });

  it("stops delivering once the subscription is disposed", () => {
    const onCommand = vi.fn();

    createCommands().onCommand(onCommand)();
    listeners.forEach((listener) => listener("clip-recipe", { id: 7 }));

    expect(onCommand).not.toHaveBeenCalled();
  });

  it("survives a browser that reports no tab with the shortcut", () => {
    const onCommand = vi.fn();
    createCommands().onCommand(onCommand);

    listeners.forEach((listener) => listener("clip-recipe"));

    expect(onCommand).toHaveBeenCalledWith({ command: "clip-recipe" });
  });
});
