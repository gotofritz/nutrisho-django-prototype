import { err, ok, type Result } from "../../result";
import { DEFAULT_SETTINGS, type Settings } from "../../settings";
import type { SettingsStore, StoreError } from "../types";

export interface FakeSettingsStore extends SettingsStore {
  failWith(error: StoreError | undefined): void;
}

/** An in-memory `SettingsStore`, starting from the defaults unless told otherwise. */
export function createFakeSettingsStore(
  initial: Settings = DEFAULT_SETTINGS,
): FakeSettingsStore {
  let stored = initial;
  let failure: StoreError | undefined;

  return {
    failWith(error: StoreError | undefined): void {
      failure = error;
    },

    async load(): Promise<Result<Settings, StoreError>> {
      return failure === undefined ? ok(stored) : err(failure);
    },

    async save(settings: Settings): Promise<Result<void, StoreError>> {
      if (failure !== undefined) return err(failure);

      stored = settings;
      return ok(undefined);
    },
  };
}
