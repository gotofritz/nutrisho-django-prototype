import { browser } from "wxt/browser";

/** A tab, reduced to what a capture needs of it. */
export interface TabRef {
  readonly id: number;
  readonly url?: string;
  readonly title?: string;
}

export interface TabsPort {
  /** The focused tab, or `undefined` when nothing is focused. */
  activeTab(): Promise<TabRef | undefined>;
}

export function createTabs(): TabsPort {
  return {
    async activeTab(): Promise<TabRef | undefined> {
      const [tab] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      // No focused tab is ordinary — a devtools window, a browser starting up.
      if (tab?.id == null) return undefined;
      return { id: tab.id, url: tab.url, title: tab.title };
    },
  };
}
