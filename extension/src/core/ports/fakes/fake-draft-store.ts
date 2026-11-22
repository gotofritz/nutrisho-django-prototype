import { EMPTY_DRAFTS, type Drafts } from "../../drafts";
import { err, ok, type Result } from "../../result";
import type { DraftStore, StoreError } from "../types";

export interface FakeDraftStore extends DraftStore {
  failWith(error: StoreError | undefined): void;
  /** How many times `save` stored something. */
  readonly saves: number;
}

/** An in-memory `DraftStore`, failable so consumers can test their error path. */
export function createFakeDraftStore(
  initial: Drafts = EMPTY_DRAFTS,
): FakeDraftStore {
  let stored = initial;
  let failure: StoreError | undefined;
  let saves = 0;

  return {
    failWith(error: StoreError | undefined): void {
      failure = error;
    },

    get saves() {
      return saves;
    },

    async load(): Promise<Result<Drafts, StoreError>> {
      return failure === undefined ? ok(stored) : err(failure);
    },

    async save(drafts: Drafts): Promise<Result<void, StoreError>> {
      if (failure !== undefined) return err(failure);
      // Browser storage keeps a structured clone, and refuses a Proxy.
      try {
        stored = structuredClone(drafts);
      } catch (cause) {
        return err({
          kind: "write-failed",
          message: cause instanceof Error ? cause.message : String(cause),
        });
      }
      saves += 1;
      return ok(undefined);
    },
  };
}
