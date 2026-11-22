import type { StoragePort } from "../storage";

export interface FakeStorage extends StoragePort {
  /** Everything stored, by key: what a test reads back. */
  readonly written: Record<string, unknown>;
  /** Make every later call throw `error`, as a full or broken store does. */
  failWith(error: Error | undefined): void;
}

/**
 * An in-memory `StoragePort`. It tells watchers about a write the way
 * `storage.onChanged` does, so a test can show the sidebar hearing about a
 * clipping the background stored.
 */
export function createFakeStorage(
  initial: Record<string, unknown> = {},
): FakeStorage {
  const written: Record<string, unknown> = { ...initial };
  const watchers = new Map<string, Set<() => void>>();
  let failure: Error | undefined;

  function check(): void {
    if (failure !== undefined) throw failure;
  }

  function changed(key: string): void {
    for (const listener of watchers.get(key) ?? []) listener();
  }

  return {
    written,

    failWith(error: Error | undefined): void {
      failure = error;
    },

    async get<T>(key: string): Promise<T | undefined> {
      check();
      return written[key] as T | undefined;
    },

    async set<T>(key: string, value: T): Promise<void> {
      check();
      written[key] = structuredClone(value);
      changed(key);
    },

    async remove(key: string): Promise<void> {
      check();
      delete written[key];
      changed(key);
    },

    onChanged(key: string, listener: () => void): () => void {
      const listeners = watchers.get(key) ?? new Set();
      listeners.add(listener);
      watchers.set(key, listeners);
      return () => listeners.delete(listener);
    },
  };
}
