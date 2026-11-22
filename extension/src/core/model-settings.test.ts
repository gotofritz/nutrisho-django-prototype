import { describe, expect, it } from "vitest";

import {
  BACKENDS,
  BUILT_IN,
  checkModelSettings,
  defaultsFor,
  modelHostPattern,
  readModelSettings,
} from "./model-settings";

const KEY = "sk-ant-api03-clipper";

// Plan 012, M13 (#181): which scanner reads the lines, and where it is.
describe("defaultsFor", () => {
  it("starts each backend where timbuktu's guide starts it", () => {
    expect(defaultsFor("mlx")).toEqual({
      backend: "mlx",
      address: "http://localhost:8080",
      model: "mlx-community/Qwen3-8B-4bit",
      key: "",
    });
    expect(defaultsFor("llama")).toEqual({
      backend: "llama",
      address: "http://localhost:8081",
      model: "",
      key: "",
    });
    expect(defaultsFor("anthropic")).toEqual({
      backend: "anthropic",
      address: "https://api.anthropic.com",
      model: "claude-haiku-5-5",
      key: "",
    });
    expect(defaultsFor("built-in")).toEqual(BUILT_IN);
  });

  it("offers the built-in scan first, then the three", () => {
    expect(BACKENDS.map((backend) => backend.id)).toEqual([
      "built-in",
      "mlx",
      "llama",
      "anthropic",
    ]);
  });
});

describe("checkModelSettings", () => {
  it("takes a local server on this computer, tidied to its origin", () => {
    expect(
      checkModelSettings({
        ...defaultsFor("mlx"),
        address: " http://127.0.0.1:8080/ ",
        model: " mlx-community/Qwen3-8B-4bit ",
      }),
    ).toEqual({
      ok: true,
      value: {
        backend: "mlx",
        address: "http://127.0.0.1:8080",
        model: "mlx-community/Qwen3-8B-4bit",
        key: "",
      },
    });
  });

  it.each([
    ["", "Enter the address the server listens at."],
    ["localhost:8080", "Enter a whole address, such as http://localhost:8080."],
    [
      "http://192.168.1.5:8080",
      "A local model runs on this computer: localhost or 127.0.0.1.",
    ],
    ["https://localhost:8080", "The address has to start with http://."],
  ])("refuses the address %j", (address, message) => {
    expect(checkModelSettings({ ...defaultsFor("llama"), address })).toEqual({
      ok: false,
      error: [{ field: "address", message }],
    });
  });

  it("needs the model's name for MLX and Anthropic, not for llama.cpp", () => {
    expect(checkModelSettings({ ...defaultsFor("llama"), model: "" }).ok).toBe(
      true,
    );
    for (const backend of ["mlx", "anthropic"] as const) {
      expect(
        checkModelSettings({ ...defaultsFor(backend), model: " ", key: KEY }),
      ).toEqual({
        ok: false,
        error: [{ field: "model", message: "Enter the model's name." }],
      });
    }
  });

  // Kept in storage.local, as the Nutrisho key is (the person chose, #181).
  it("needs an Anthropic key, and tidies it", () => {
    expect(
      checkModelSettings({ ...defaultsFor("anthropic"), key: ` ${KEY} ` }),
    ).toEqual({ ok: true, value: { ...defaultsFor("anthropic"), key: KEY } });
    expect(checkModelSettings(defaultsFor("anthropic"))).toEqual({
      ok: false,
      error: [{ field: "key", message: "Enter your Anthropic key." }],
    });
    expect(
      checkModelSettings({ ...defaultsFor("anthropic"), key: "nsh_abc" }),
    ).toEqual({
      ok: false,
      error: [
        {
          field: "key",
          message: "That is not an Anthropic key: one starts with sk-ant-.",
        },
      ],
    });
  });

  it("keeps Anthropic at its own address, whatever was typed", () => {
    const checked = checkModelSettings({
      ...defaultsFor("anthropic"),
      address: "http://localhost:1",
      key: KEY,
    });

    expect(checked.ok && checked.value.address).toBe(
      "https://api.anthropic.com",
    );
  });

  it("takes the built-in scan as it is", () => {
    expect(checkModelSettings(BUILT_IN)).toEqual({ ok: true, value: BUILT_IN });
  });
});

describe("readModelSettings", () => {
  it("reads what was saved", () => {
    expect(readModelSettings(defaultsFor("llama"))).toEqual(
      defaultsFor("llama"),
    );
  });

  it.each([
    undefined,
    null,
    "mlx",
    { backend: "ollama" },
    { backend: "mlx", address: 3 },
  ])("falls back to the built-in scan for %j", (stored) => {
    expect(readModelSettings(stored)).toEqual(BUILT_IN);
  });
});

describe("modelHostPattern", () => {
  it("asks for the model's host, by its match pattern", () => {
    expect(modelHostPattern(defaultsFor("mlx"))).toBe("http://localhost/*");
    expect(modelHostPattern(defaultsFor("anthropic"))).toBe(
      "https://api.anthropic.com/*",
    );
    expect(modelHostPattern(BUILT_IN)).toBeUndefined();
  });
});
