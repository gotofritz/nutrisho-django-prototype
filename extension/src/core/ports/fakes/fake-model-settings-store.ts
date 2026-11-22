import { BUILT_IN, type ModelSettings } from "../../model-settings";
import { err, ok } from "../../result";
import type { ModelSettingsStore, StoreError } from "../types";

export interface FakeModelSettingsStore extends ModelSettingsStore {
  failWith(error: StoreError | undefined): void;
}

/** An in-memory `ModelSettingsStore`, starting from the built-in scan. */
export function createFakeModelSettingsStore(
  initial: ModelSettings = BUILT_IN,
): FakeModelSettingsStore {
  let stored = initial;
  let failure: StoreError | undefined;
  return {
    failWith(error) {
      failure = error;
    },
    async load() {
      return failure === undefined ? ok(stored) : err(failure);
    },
    async save(settings) {
      if (failure !== undefined) return err(failure);
      stored = settings;
      return ok(undefined);
    },
  };
}
