import type { SettingsStore, StoreError } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";
import { DEFAULT_SETTINGS, readSettings, type Settings } from "@/core/settings";

import type { StoragePort } from "./storage";

/**
 * `SettingsStore` over extension storage (plan 012, M6).
 *
 * `storage.local`, never `sync`: the API key is never synced (D11). The read
 * path validates and degrades, and never trusts: the only failure it reports
 * is storage itself refusing.
 */
export const SETTINGS_KEY = "settings";

function fail(kind: StoreError["kind"], cause: unknown): StoreError {
  return {
    kind,
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export function createStoredSettings(storage: StoragePort): SettingsStore {
  return {
    async load(): Promise<Result<Settings, StoreError>> {
      try {
        return ok(readSettings(await storage.get<unknown>(SETTINGS_KEY)));
      } catch (cause) {
        return err(fail("read-failed", cause));
      }
    },

    async save(settings: Settings): Promise<Result<void, StoreError>> {
      try {
        await storage.set(SETTINGS_KEY, {
          serverUrl: settings.serverUrl,
          apiKey: settings.apiKey,
        });
        return ok(undefined);
      } catch (cause) {
        return err(fail("write-failed", cause));
      }
    },
  };
}

/**
 * The read that cannot fail. Most callers have nothing useful to do with a
 * storage failure, so they get the defaults; the options page is the one
 * caller that wants the failure, and uses `load` directly.
 */
export async function loadSettingsOrDefaults(
  store: SettingsStore,
): Promise<Settings> {
  const stored = await store.load();

  return stored.ok ? stored.value : DEFAULT_SETTINGS;
}
