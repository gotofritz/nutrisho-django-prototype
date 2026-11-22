import { describe, expect, it } from "vitest";

import { BUILT_IN, defaultsFor } from "../../model-settings";
import { createFakeModelSettingsStore } from "./fake-model-settings-store";

describe("createFakeModelSettingsStore", () => {
  it("starts from the built-in scan, and keeps what is saved", async () => {
    const store = createFakeModelSettingsStore();
    expect(await store.load()).toEqual({ ok: true, value: BUILT_IN });

    await store.save(defaultsFor("mlx"));

    expect(await store.load()).toEqual({ ok: true, value: defaultsFor("mlx") });
  });

  it("can fail the way storage does", async () => {
    const store = createFakeModelSettingsStore();
    store.failWith({ kind: "write-failed", message: "full" });

    expect(await store.save(BUILT_IN)).toEqual({
      ok: false,
      error: { kind: "write-failed", message: "full" },
    });
  });
});
