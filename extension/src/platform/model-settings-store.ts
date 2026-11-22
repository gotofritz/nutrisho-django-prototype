import type { ModelSettingsStore, StoreError } from "@/core/ports/types";
import { readModelChoices } from "@/core/model-settings";
import { err, ok } from "@/core/result";

import type { StoragePort } from "./storage";

/**
 * `ModelSettingsStore` over `storage.local` (plan 012, M13), beside the
 * Nutrisho settings and never synced: every set-up, keys included (D11),
 * and the default (#183).
 */
export const MODEL_SETTINGS_KEY = "model";

function fail(kind: StoreError["kind"], cause: unknown): StoreError {
  return {
    kind,
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export function createStoredModelSettings(
  storage: StoragePort,
): ModelSettingsStore {
  return {
    async load() {
      try {
        return ok(
          readModelChoices(await storage.get<unknown>(MODEL_SETTINGS_KEY)),
        );
      } catch (cause) {
        return err(fail("read-failed", cause));
      }
    },
    async save(choices) {
      try {
        // Plain copies: browser storage refuses to clone a Svelte proxy.
        await storage.set(MODEL_SETTINGS_KEY, {
          setups: choices.setups.map((setup) => ({ ...setup })),
          chosen: choices.chosen,
        });
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },
  };
}

/**
 * Watch for the set-ups changing, so the sidebar asks the default at once
 * rather than when it next opens.
 */
export function watchModelSettings(
  storage: StoragePort,
  listener: () => void,
): () => void {
  return storage.onChanged(MODEL_SETTINGS_KEY, listener);
}
