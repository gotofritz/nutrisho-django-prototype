import {
  choicesFrom,
  type ModelChoices,
  type ModelSettings,
  NO_CHOICES,
} from "../../model-settings";
import { err, ok } from "../../result";
import type { ModelSettingsStore, StoreError } from "../types";

export interface FakeModelSettingsStore extends ModelSettingsStore {
  failWith(error: StoreError | undefined): void;
}

/**
 * An in-memory `ModelSettingsStore`, with no set-ups, or with one model as
 * its only set-up and the default, as a model saved before #183 is read.
 */
export function createFakeModelSettingsStore(
  initial: ModelChoices | ModelSettings = NO_CHOICES,
): FakeModelSettingsStore {
  let stored = "setups" in initial ? initial : choicesFrom(initial);
  let failure: StoreError | undefined;
  return {
    failWith(error) {
      failure = error;
    },
    async load() {
      return failure === undefined ? ok(stored) : err(failure);
    },
    async save(choices) {
      if (failure !== undefined) return err(failure);
      stored = choices;
      return ok(undefined);
    },
  };
}
