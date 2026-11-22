import { describe, expect, it } from "vitest";

import {
  BUILT_IN,
  NO_CHOICES,
  choicesFrom,
  defaultsFor,
} from "../../model-settings";
import { createFakeModelSettingsStore } from "./fake-model-settings-store";

describe("createFakeModelSettingsStore", () => {
  it("starts with no set-ups, and keeps what is saved", async () => {
    const store = createFakeModelSettingsStore();
    expect(await store.load()).toEqual({ ok: true, value: NO_CHOICES });

    await store.save(choicesFrom(defaultsFor("mlx")));

    expect(await store.load()).toEqual({
      ok: true,
      value: choicesFrom(defaultsFor("mlx")),
    });
  });

  it("starts from one model, as its only set-up and the default", async () => {
    const store = createFakeModelSettingsStore(defaultsFor("llama"));

    expect(await store.load()).toEqual({
      ok: true,
      value: choicesFrom(defaultsFor("llama")),
    });
    expect(await createFakeModelSettingsStore(BUILT_IN).load()).toEqual({
      ok: true,
      value: NO_CHOICES,
    });
  });

  it("can fail the way storage does", async () => {
    const store = createFakeModelSettingsStore();
    store.failWith({ kind: "write-failed", message: "full" });

    expect(await store.save(NO_CHOICES)).toEqual({
      ok: false,
      error: { kind: "write-failed", message: "full" },
    });
  });
});
