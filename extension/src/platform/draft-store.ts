import { EMPTY_DRAFTS, isDrafts, type Drafts } from "@/core/drafts";
import type { DraftStore, StoreError } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";

import type { StoragePort } from "./storage";

/**
 * `DraftStore` over extension storage (plan 012, M7), so a draft survives the
 * sidebar closing. `storage.local`, like everything here: a draft is page
 * content, and is never synced.
 */
export const DRAFTS_KEY = "drafts";

function fail(kind: StoreError["kind"], cause: unknown): StoreError {
  return {
    kind,
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export function createStoredDrafts(storage: StoragePort): DraftStore {
  return {
    async load(): Promise<Result<Drafts, StoreError>> {
      let stored: unknown;
      try {
        stored = await storage.get<unknown>(DRAFTS_KEY);
      } catch (cause) {
        return err(fail("read-failed", cause));
      }

      if (stored === undefined) return ok(EMPTY_DRAFTS);
      if (!isDrafts(stored)) {
        return err({
          kind: "malformed-stored-value",
          message: "what is stored under the drafts key is not drafts",
        });
      }
      return ok(stored);
    },

    async save(drafts: Drafts): Promise<Result<void, StoreError>> {
      try {
        await storage.set(DRAFTS_KEY, drafts);
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },
  };
}
