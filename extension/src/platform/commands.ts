import { browser } from "wxt/browser";

/** A keyboard shortcut firing, reduced to what a capture needs of it. */
export interface CommandInvocation {
  readonly command: string;
  /** Absent when the browser reports no tab — a shortcut in a popup window. */
  readonly tabId?: number;
}

/**
 * Keyboard shortcuts. `commands` is a manifest key rather than a
 * permission, so this adds nothing to the ceiling; the shortcut it declares
 * is the same gesture as the context-menu entry and takes the same path.
 */
export interface CommandsPort {
  onCommand(listener: (invocation: CommandInvocation) => void): () => void;
}

export function createCommands(): CommandsPort {
  return {
    onCommand(listener: (invocation: CommandInvocation) => void): () => void {
      const wrapped = (command: string, tab?: { id?: number }) => {
        listener({
          command,
          ...(tab?.id == null ? {} : { tabId: tab.id }),
        });
      };
      browser.commands.onCommand.addListener(wrapped);
      return () => browser.commands.onCommand.removeListener(wrapped);
    },
  };
}
