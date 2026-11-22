import { describe, expect, it } from "vitest";

import {
  BACKENDS,
  BUILT_IN,
  checkModelSettings,
  defaultsFor,
  NO_CHOICES,
  checkSetupName,
  chooseSetup,
  choicesFrom,
  chosenSettings,
  chosenSetup,
  modelHostPattern,
  readModelChoices,
  readModelSettings,
  removeSetup,
  saveSetup,
  suggestName,
  type ModelChoices,
  type ModelSetup,
  type UnsavedSetup,
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

// #183: several set-ups, one of them the default.
const MLX = { ...defaultsFor("mlx"), id: "1", name: "Qwen on MLX" };
const HAIKU = {
  ...defaultsFor("anthropic"),
  key: KEY,
  id: "2",
  name: "Haiku",
};
const BOTH: ModelChoices = { setups: [MLX, HAIKU], chosen: "1" };

/** A set-up as the form hands it over, before it has an id. */
function unsaved(setup: ModelSetup): UnsavedSetup {
  const { backend, address, model, key, name } = setup;
  return { backend, address, model, key, name };
}

describe("choicesFrom", () => {
  it("makes the one model saved before #183 the first set-up, and the default", () => {
    expect(choicesFrom(defaultsFor("mlx"))).toEqual({
      setups: [
        { ...defaultsFor("mlx"), id: "1", name: "Qwen3-8B-4bit on MLX" },
      ],
      chosen: "1",
    });
  });

  it("has nothing to carry over from the built-in scan", () => {
    expect(choicesFrom(BUILT_IN)).toEqual(NO_CHOICES);
  });
});

describe("readModelChoices", () => {
  it("reads what was saved", () => {
    expect(readModelChoices(BOTH)).toEqual(BOTH);
  });

  it("reads the single model saved before #183", () => {
    expect(readModelChoices(defaultsFor("llama"))).toEqual(
      choicesFrom(defaultsFor("llama")),
    );
  });

  it("drops a set-up it cannot read, and a default that is gone", () => {
    expect(
      readModelChoices({
        setups: [
          MLX,
          { ...HAIKU, name: 3 },
          { ...BUILT_IN, id: "4", name: "x" },
        ],
        chosen: "2",
      }),
    ).toEqual({ setups: [MLX], chosen: undefined });
  });

  it("starts with none from nothing", () => {
    expect(readModelChoices(undefined)).toEqual(NO_CHOICES);
    expect(readModelChoices("mlx")).toEqual(NO_CHOICES);
  });
});

describe("chosenSetup", () => {
  it("gives the default set-up, or none for the built-in scan", () => {
    expect(chosenSetup(BOTH)).toEqual(MLX);
    expect(chosenSetup({ ...BOTH, chosen: undefined })).toBeUndefined();
  });
});

describe("chosenSettings", () => {
  it("gives the adapters the default set-up, less its name", () => {
    expect(chosenSettings(BOTH)).toEqual(defaultsFor("mlx"));
    expect(chosenSettings(NO_CHOICES)).toEqual(BUILT_IN);
  });
});

describe("suggestName", () => {
  it("names a set-up by its model and where it runs", () => {
    expect(suggestName(defaultsFor("mlx"))).toBe("Qwen3-8B-4bit on MLX");
    expect(suggestName(defaultsFor("anthropic"))).toBe(
      "claude-haiku-5-5 on Anthropic",
    );
    expect(suggestName(defaultsFor("llama"))).toBe("llama.cpp");
    expect(suggestName({ ...defaultsFor("llama"), model: "qwen3" })).toBe(
      "qwen3 on llama.cpp",
    );
  });
});

describe("saveSetup", () => {
  it("adds a set-up with an id of its own", () => {
    const added = saveSetup({ setups: [MLX], chosen: "1" }, unsaved(HAIKU));

    expect(added.setups).toEqual([MLX, HAIKU]);
    expect(added.chosen).toBe("1");
  });

  it("makes the first set-up the default", () => {
    expect(saveSetup(NO_CHOICES, unsaved(MLX))).toEqual({
      setups: [MLX],
      chosen: "1",
    });
  });

  it("leaves the built-in scan chosen once there are set-ups", () => {
    expect(
      saveSetup({ setups: [MLX], chosen: undefined }, unsaved(HAIKU)).chosen,
    ).toBeUndefined();
  });

  it("changes a set-up in its place", () => {
    const renamed = { ...MLX, name: "Local" };
    expect(saveSetup(BOTH, renamed).setups).toEqual([renamed, HAIKU]);
  });
});

describe("removeSetup", () => {
  it("removes a set-up", () => {
    expect(removeSetup(BOTH, "2")).toEqual({ setups: [MLX], chosen: "1" });
  });

  it("goes back to the built-in scan when the default goes", () => {
    expect(removeSetup(BOTH, "1")).toEqual({
      setups: [HAIKU],
      chosen: undefined,
    });
  });
});

describe("chooseSetup", () => {
  it("makes a set-up the default, or the built-in scan", () => {
    expect(chooseSetup(BOTH, "2").chosen).toBe("2");
    expect(chooseSetup(BOTH, undefined).chosen).toBeUndefined();
  });

  it("ignores a set-up it does not have", () => {
    expect(chooseSetup(BOTH, "9")).toBe(BOTH);
  });
});

describe("checkSetupName", () => {
  it("needs a name, unlike the others ignoring case", () => {
    expect(checkSetupName({ name: "  ", choices: BOTH })).toBe(
      "Give the set-up a name.",
    );
    expect(checkSetupName({ name: "haiku ", choices: BOTH })).toBe(
      "Another set-up has that name.",
    );
    expect(checkSetupName({ name: "Haiku", choices: BOTH, id: "2" })).toBe(
      undefined,
    );
    expect(checkSetupName({ name: "Sonnet", choices: BOTH })).toBe(undefined);
  });
});
