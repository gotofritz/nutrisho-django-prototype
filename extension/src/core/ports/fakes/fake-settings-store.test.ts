import { describe, expect, it } from "vitest";

import { isErr, isOk } from "../../result";
import { DEFAULT_SETTINGS } from "../../settings";
import { createFakeSettingsStore } from "./fake-settings-store";

const SAVED = {
  serverUrl: "http://127.0.0.1:8000",
  apiKey: "nsh_example",
};

describe("createFakeSettingsStore", () => {
  it("holds the defaults to begin with", async () => {
    const result = await createFakeSettingsStore().load();

    expect(isOk(result) && result.value).toEqual(DEFAULT_SETTINGS);
  });

  it("gives back what was saved", async () => {
    const store = createFakeSettingsStore();

    await store.save(SAVED);

    expect(await store.load()).toEqual({ ok: true, value: SAVED });
  });

  it("can start from saved settings", async () => {
    expect(await createFakeSettingsStore(SAVED).load()).toEqual({
      ok: true,
      value: SAVED,
    });
  });

  it("can be driven into failure and reports it in the port's error shape", async () => {
    const store = createFakeSettingsStore();
    store.failWith({ kind: "read-failed", message: "storage is gone" });

    expect(isErr(await store.load())).toBe(true);
    expect(isErr(await store.save(SAVED))).toBe(true);
  });
});
