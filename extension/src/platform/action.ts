import { browser } from "wxt/browser";

/** A click on the toolbar button, reduced to what a capture needs of it. */
export interface ActionClick {
  readonly tabId?: number;
  readonly pageUrl?: string;
}

/**
 * The toolbar button (plan 012, M6). `action` is a manifest key, not a
 * permission, and with no popup a click arrives here: the background opens
 * the sidebar and clips whatever is selected.
 */
export interface ActionPort {
  onClicked(listener: (click: ActionClick) => void): () => void;
}

export function createAction(): ActionPort {
  return {
    onClicked(listener: (click: ActionClick) => void): () => void {
      const wrapped = (tab: { id?: number; url?: string }) => {
        listener({
          ...(tab.id == null ? {} : { tabId: tab.id }),
          ...(tab.url === undefined ? {} : { pageUrl: tab.url }),
        });
      };
      browser.action.onClicked.addListener(wrapped);
      return () => browser.action.onClicked.removeListener(wrapped);
    },
  };
}
