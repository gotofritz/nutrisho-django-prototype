import { describe, expect, it, vi } from "vitest";

import { NO_CHOICES, choicesFrom, defaultsFor } from "@/core/model-settings";

import { createFakeStorage } from "./fakes/fake-storage";
import {
  MODEL_SETTINGS_KEY,
  createStoredModelSettings,
  watchModelSettings,
} from "./model-settings-store";

describe("stored model settings", () => {
  it("hold no set-ups until something is saved", async () => {
    expect(await createStoredModelSettings(createFakeStorage()).load()).toEqual(
      { ok: true, value: NO_CHOICES },
    );
  });

  it("round-trip through storage, under their own key", async () => {
    const storage = createFakeStorage();
    const store = createStoredModelSettings(storage);
    const choices = choicesFrom(defaultsFor("llama"));

    await store.save(choices);

    expect(await storage.get(MODEL_SETTINGS_KEY)).toEqual(choices);
    expect(await store.load()).toEqual({ ok: true, value: choices });
  });

  // #183: the one model saved before is kept, as the first set-up.
  it("read the single model saved before set-ups", async () => {
    const storage = createFakeStorage();
    await storage.set(MODEL_SETTINGS_KEY, defaultsFor("mlx"));

    expect(await createStoredModelSettings(storage).load()).toEqual({
      ok: true,
      value: choicesFrom(defaultsFor("mlx")),
    });
  });

  it("read anything else as no set-ups", async () => {
    const storage = createFakeStorage();
    await storage.set(MODEL_SETTINGS_KEY, { backend: "ollama" });

    expect(await createStoredModelSettings(storage).load()).toEqual({
      ok: true,
      value: NO_CHOICES,
    });
  });
});

// The sidebar reloads its model when a set-up is saved.
describe("watchModelSettings", () => {
  it("tells the sidebar when a model is saved", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();
    watchModelSettings(storage, changed);

    await createStoredModelSettings(storage).save(
      choicesFrom(defaultsFor("mlx")),
    );

    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("stops telling it once disposed", async () => {
    const storage = createFakeStorage();
    const changed = vi.fn();

    watchModelSettings(storage, changed)();
    await createStoredModelSettings(storage).save(
      choicesFrom(defaultsFor("mlx")),
    );

    expect(changed).not.toHaveBeenCalled();
  });
});
