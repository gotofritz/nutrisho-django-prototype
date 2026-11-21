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

/**
 * `local` keeps a value until it is removed: the settings. `session` keeps it
 * while the browser runs, so a new browser session starts without the last
 * one's clipping and drafts, which are page content (M7). Neither is synced.
 */
export type StorageArea = "local" | "session";

export function createStorage(area: StorageArea = "local"): StoragePort {
  const store = () => browser.storage[area];
  return {
    async get<T>(key: string): Promise<T | undefined> {
      const stored = await store().get(key);
      return stored[key] as T | undefined;
    },

    async set<T>(key: string, value: T): Promise<void> {
      await store().set({ [key]: value });
    },

    async remove(key: string): Promise<void> {
      await store().remove(key);
    },

    onChanged(key: string, listener: () => void): () => void {
      // `storage.onChanged` with an area check rather than the area's own
      // `onChanged`: both browsers have the former.
      const wrapped = (changes: Record<string, unknown>, areaName: string) => {
        if (areaName === area && key in changes) listener();
      };
      browser.storage.onChanged.addListener(wrapped);
      return () => browser.storage.onChanged.removeListener(wrapped);
    },
  };
}
