import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS } from "@/core/settings";

import { createFakeStorage } from "./fakes/fake-storage";
import {
  SETTINGS_KEY,
  createStoredSettings,
  loadSettingsOrDefaults,
} from "./settings-store";

const SAVED = {
  serverUrl: "http://127.0.0.1:8000",
  apiKey: "nsh_abcdefghijklmnop",
};

describe("stored settings", () => {
  it("are the defaults until something is saved", async () => {
    expect(await createStoredSettings(createFakeStorage()).load()).toEqual({
      ok: true,
      value: DEFAULT_SETTINGS,
    });
  });

  it("round-trip through storage, under their own key", async () => {
    const storage = createFakeStorage();
    const settings = createStoredSettings(storage);

    await settings.save(SAVED);

    expect(storage.written[SETTINGS_KEY]).toEqual(SAVED);
    expect(await settings.load()).toEqual({ ok: true, value: SAVED });
  });

  // Read, never trusted: a value that does not check degrades to its default.
  it("degrade a stored value that does not check", async () => {
    const storage = createFakeStorage({
      [SETTINGS_KEY]: {
        serverUrl: "http://evil.example",
        apiKey: SAVED.apiKey,
      },
    });

    expect(await createStoredSettings(storage).load()).toEqual({
      ok: true,
      value: { serverUrl: DEFAULT_SETTINGS.serverUrl, apiKey: SAVED.apiKey },
    });
  });

  it("report storage refusing, rather than throwing", async () => {
    const storage = createFakeStorage();
    storage.failWith(new Error("storage is gone"));
    const settings = createStoredSettings(storage);

    expect(await settings.load()).toEqual({
      ok: false,
      error: { kind: "read-failed", message: "storage is gone" },
    });
    expect(await settings.save(SAVED)).toEqual({
      ok: false,
      error: { kind: "write-failed", message: "storage is gone" },
    });
  });
});

describe("loadSettingsOrDefaults", () => {
  it("is what was saved", async () => {
    const settings = createStoredSettings(createFakeStorage());
    await settings.save(SAVED);

    expect(await loadSettingsOrDefaults(settings)).toEqual(SAVED);
  });

  it("is the defaults when storage refuses", async () => {
    const storage = createFakeStorage();
    storage.failWith(new Error("storage is gone"));

    expect(await loadSettingsOrDefaults(createStoredSettings(storage))).toEqual(
      DEFAULT_SETTINGS,
    );
  });
});
