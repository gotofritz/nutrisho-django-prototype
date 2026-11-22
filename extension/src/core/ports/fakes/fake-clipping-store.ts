import type { Clipping } from "../../clipping";
import { err, ok, type Result } from "../../result";
import type { ClippingStore, StoreError } from "../types";

export interface FakeClippingStore extends ClippingStore {
  failWith(error: StoreError | undefined): void;
}

/** An in-memory `ClippingStore`, failable so consumers can test their error path. */
export function createFakeClippingStore(initial?: Clipping): FakeClippingStore {
  let stored: Clipping | undefined = initial;
  let failure: StoreError | undefined;

  function refuse<T>(): Result<T, StoreError> | undefined {
    return failure === undefined ? undefined : err(failure);
  }

  return {
    failWith(error: StoreError | undefined): void {
      failure = error;
    },

    async load(): Promise<Result<Clipping | undefined, StoreError>> {
      return refuse<Clipping | undefined>() ?? ok(stored);
    },

    async save(clipping: Clipping): Promise<Result<void, StoreError>> {
      const refused = refuse<void>();
      if (refused) return refused;

      stored = clipping;
      return ok(undefined);
    },

    async clear(): Promise<Result<void, StoreError>> {
      const refused = refuse<void>();
      if (refused) return refused;

      stored = undefined;
      return ok(undefined);
    },
  };
}
