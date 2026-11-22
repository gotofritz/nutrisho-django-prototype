import type { Clipping } from "@/core/clipping";
import { isClipping } from "@/core/clipping";
import type { ClippingStore, StoreError } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";

import type { StoragePort } from "./storage";

/**
 * `ClippingStore` over extension storage (plan 012, M6). The background is
 * unloaded when idle, so a capture writes its clipping here, and the sidebar
 * reads it back, whichever of the two finishes first.
 */
export const CLIPPING_KEY = "clipping";

function fail(kind: StoreError["kind"], cause: unknown): StoreError {
  return {
    kind,
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export function createStoredClipping(storage: StoragePort): ClippingStore {
  return {
    async load(): Promise<Result<Clipping | undefined, StoreError>> {
      let stored: unknown;
      try {
        stored = await storage.get<unknown>(CLIPPING_KEY);
      } catch (cause) {
        return err(fail("read-failed", cause));
      }

      if (stored === undefined) return ok(undefined);
      // Written by another version, or by something else entirely.
      if (!isClipping(stored)) {
        return err({
          kind: "malformed-stored-value",
          message: "what is stored under the clipping key is not a clipping",
        });
      }
      return ok(stored);
    },

    async save(clipping: Clipping): Promise<Result<void, StoreError>> {
      try {
        await storage.set(CLIPPING_KEY, clipping);
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },

    async clear(): Promise<Result<void, StoreError>> {
      try {
        await storage.remove(CLIPPING_KEY);
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },
  };
}

/**
 * Watch for a clipping written by another context. The sidebar reads the
 * clipping when it opens, and on Firefox it is usually already open when the
 * next capture happens, so without this it would go on showing the last one.
 */
export function watchClipping(
  storage: StoragePort,
  listener: () => void,
): () => void {
  return storage.onChanged(CLIPPING_KEY, listener);
}
