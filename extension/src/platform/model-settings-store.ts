import type { ModelSettingsStore, StoreError } from "@/core/ports/types";
import { readModelSettings } from "@/core/model-settings";
import { err, ok } from "@/core/result";

import type { StoragePort } from "./storage";

/**
 * `ModelSettingsStore` over `storage.local` (plan 012, M13), beside the
 * Nutrisho settings and never synced. It holds no Anthropic key.
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
          readModelSettings(await storage.get<unknown>(MODEL_SETTINGS_KEY)),
        );
      } catch (cause) {
        return err(fail("read-failed", cause));
      }
    },
    async save(settings) {
      try {
        await storage.set(MODEL_SETTINGS_KEY, { ...settings });
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },
  };
}

/**
 * Watch for a model saved on the options page, so an open sidebar offers
 * *Ask the model* at once rather than when it next opens.
 */
export function watchModelSettings(
  storage: StoragePort,
  listener: () => void,
): () => void {
  return storage.onChanged(MODEL_SETTINGS_KEY, listener);
}
