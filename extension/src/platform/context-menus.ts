import { browser } from "wxt/browser";

export type ContextMenuContext = "selection" | "page";

export interface ContextMenuItem {
  readonly id: string;
  readonly title: string;
  /** Non-empty: the browsers reject an item that matches no context. */
  readonly contexts: readonly [ContextMenuContext, ...ContextMenuContext[]];
}

export interface ContextMenuClick {
  readonly menuItemId: string;
  readonly tabId?: number;
  /**
   * The browser's own copy of the selection: truncated, plain, and with no
   * surroundings, so 5.1 re-reads the page instead. It is kept because it is
   * the only text available when no content script can run there.
   */
  readonly selectionText?: string;
  readonly pageUrl?: string;
}

/**
 * Context menu entries. The menu itself, and the code that handles a
 * click, are in `background/start.ts`.
 */
export interface ContextMenusPort {
  create(item: ContextMenuItem): Promise<void>;
  /** The background re-registers its menus on every start; this avoids duplicates. */
  removeAll(): Promise<void>;
  onClicked(listener: (click: ContextMenuClick) => void): () => void;
}

export function createContextMenus(): ContextMenusPort {
  return {
    async create(item: ContextMenuItem): Promise<void> {
      browser.contextMenus.create({
        id: item.id,
        title: item.title,
        contexts: [...item.contexts] as [
          ContextMenuContext,
          ...ContextMenuContext[],
        ],
      });
    },

    async removeAll(): Promise<void> {
      await browser.contextMenus.removeAll();
    },

    onClicked(listener: (click: ContextMenuClick) => void): () => void {
      const wrapped = (
        info: {
          menuItemId: string | number;
          selectionText?: string;
          pageUrl?: string;
        },
        tab?: { id?: number },
      ) => {
        listener({
          menuItemId: String(info.menuItemId),
          tabId: tab?.id,
          ...(info.selectionText === undefined
            ? {}
            : { selectionText: info.selectionText }),
          ...(info.pageUrl === undefined ? {} : { pageUrl: info.pageUrl }),
        });
      };
      browser.contextMenus.onClicked.addListener(wrapped);
      return () => browser.contextMenus.onClicked.removeListener(wrapped);
    },
  };
}
