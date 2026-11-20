import { browser } from "wxt/browser";

/**
 * Extension storage.
 *
 * Firefox's event page and Chrome's service worker are both unloaded when
 * idle, so nothing durable may live in module scope. Anything that has to
 * survive goes through here from the start.
 */
export interface StoragePort {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T): Promise<void>;
  remove(key: string): Promise<void>;
  /**
   * Watch one key. This is how a context learns about a write it did not
   * make: the sidebar persists per window on Firefox, so a capture usually
   * happens while it is already open and has already read the clipping once.
   */
  onChanged(key: string, listener: () => void): () => void;
}

export function createStorage(): StoragePort {
  return {
    async get<T>(key: string): Promise<T | undefined> {
      const stored = await browser.storage.local.get(key);
      return stored[key] as T | undefined;
    },

    async set<T>(key: string, value: T): Promise<void> {
      await browser.storage.local.set({ [key]: value });
    },

    async remove(key: string): Promise<void> {
      await browser.storage.local.remove(key);
    },

    onChanged(key: string, listener: () => void): () => void {
      // `storage.onChanged` with an area check rather than
      // `storage.local.onChanged`: both browsers have the former, and only
      // the local area is written here.
      const wrapped = (changes: Record<string, unknown>, areaName: string) => {
        if (areaName === "local" && key in changes) listener();
      };
      browser.storage.onChanged.addListener(wrapped);
      return () => browser.storage.onChanged.removeListener(wrapped);
    },
  };
}
