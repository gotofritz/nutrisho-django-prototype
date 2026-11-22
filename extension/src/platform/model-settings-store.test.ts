import { describe, expect, it, vi } from "vitest";

import { BUILT_IN, defaultsFor } from "@/core/model-settings";

import { createFakeStorage } from "./fakes/fake-storage";
import {
  MODEL_SETTINGS_KEY,
  createStoredModelSettings,
  watchModelSettings,
} from "./model-settings-store";

describe("stored model settings", () => {
  it("are the built-in scan until something is saved", async () => {
    expect(await createStoredModelSettings(createFakeStorage()).load()).toEqual(
      { ok: true, value: BUILT_IN },
    );
  });

  it("round-trip through storage, under their own key", async () => {
    const storage = createFakeStorage();
    const store = createStoredModelSettings(storage);

    await store.save(defaultsFor("llama"));

    expect(await storage.get(MODEL_SETTINGS_KEY)).toEqual(defaultsFor("llama"));
    expect(await store.load()).toEqual({
      ok: true,
      value: defaultsFor("llama"),
    });
  });

  it("reads anything else as the built-in scan", async () => {
    const storage = createFakeStorage();
    await storage.set(MODEL_SETTINGS_KEY, { backend: "ollama" });

    expect(await createStoredModelSettings(storage).load()).toEqual({
      ok: true,
      value: BUILT_IN,
    });
  });
});

// The sidebar is often open while the options page saves a model.
describe("watchModelSettings", () => {
  it("tells the sidebar when the options page saves a model", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();
    watchModelSettings(storage, changed);

    await createStoredModelSettings(storage).save(defaultsFor("mlx"));

    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("stops telling it once disposed", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();

    watchModelSettings(storage, changed)();
    await createStoredModelSettings(storage).save(defaultsFor("mlx"));

    expect(changed).not.toHaveBeenCalled();
  });
});
