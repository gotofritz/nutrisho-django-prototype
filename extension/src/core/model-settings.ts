import { LOOPBACK_HOSTS, MODEL_HOST } from "@/manifest/manifest";

import { err, ok, type Result } from "./result";

/**
 * Which scanner reads ingredient lines, and where its model is (plan 012,
 * M13, D20): the built-in one, or the user's own model on one of timbuktu's
 * three backends. Its key, a local server's or the user's own Anthropic
 * key, is kept as the Nutrisho key is (D11): in `storage.local`, never
 * synced, logged or shown again.
 */
export type ModelBackend = "built-in" | "mlx" | "llama" | "anthropic";

export interface ModelSettings {
  readonly backend: ModelBackend;
  /** Where the server listens; Anthropic's own for Anthropic, "" built in. */
  readonly address: string;
  /** The model's name; "" lets a llama.cpp server with one model use it. */
  readonly model: string;
  /** Anthropic's key, or a local server's own when it asks for one; "" otherwise. */
  readonly key: string;
}

export type ModelField = "address" | "model" | "key";

export interface ModelIssue {
  readonly field: ModelField;
  readonly message: string;
}

export const BUILT_IN: ModelSettings = {
  backend: "built-in",
  address: "",
  model: "",
  key: "",
};

export const ANTHROPIC_ADDRESS = `https://${MODEL_HOST}`;

export const BACKENDS: readonly { id: ModelBackend; label: string }[] = [
  { id: "built-in", label: "Built in" },
  { id: "mlx", label: "MLX, on this Mac" },
  { id: "llama", label: "llama.cpp, on this computer" },
  { id: "anthropic", label: "Anthropic, with your own key" },
];

const DEFAULTS: Readonly<Record<ModelBackend, ModelSettings>> = {
  "built-in": BUILT_IN,
  // `mlx_lm.server --model mlx-community/Qwen3-8B-4bit --port 8080`
  mlx: {
    backend: "mlx",
    address: "http://localhost:8080",
    model: "mlx-community/Qwen3-8B-4bit",
    key: "",
  },
  // `llama-server -hf unsloth/Qwen3-8B-GGUF:UD-Q4_K_XL --port 8081`
  llama: {
    backend: "llama",
    address: "http://localhost:8081",
    model: "",
    key: "",
  },
  // Splitting short lines needs a quick, cheap model.
  anthropic: {
    backend: "anthropic",
    address: ANTHROPIC_ADDRESS,
    model: "claude-haiku-5-5",
    key: "",
  },
};

export function defaultsFor(backend: ModelBackend): ModelSettings {
  return DEFAULTS[backend];
}

const LOOPBACK: readonly string[] = LOOPBACK_HOSTS;

/** `sk-ant-` and no spaces: enough to catch a key pasted in the wrong box. */
const ANTHROPIC_KEY = /^sk-ant-\S+$/;

function checkAddress(input: string): Result<string, ModelIssue> {
  const typed = input.trim();
  const problem = (message: string) =>
    err({ field: "address", message } as const);
  if (typed === "") return problem("Enter the address the server listens at.");
  let url: URL;
  try {
    if (!typed.includes("://")) throw new TypeError("no scheme");
    url = new URL(typed);
  } catch {
    return problem("Enter a whole address, such as http://localhost:8080.");
  }
  if (!LOOPBACK.includes(url.hostname)) {
    return problem(
      "A local model runs on this computer: localhost or 127.0.0.1.",
    );
  }
  if (url.protocol !== "http:") {
    return problem("The address has to start with http://.");
  }
  return ok(url.origin);
}

/** What the user chose, checked and tidied; every problem at once. */
export function checkModelSettings(
  input: ModelSettings,
): Result<ModelSettings, readonly ModelIssue[]> {
  if (input.backend === "built-in") return ok(BUILT_IN);
  const issues: ModelIssue[] = [];
  let address = ANTHROPIC_ADDRESS;
  if (input.backend !== "anthropic") {
    const checked = checkAddress(input.address);
    if (checked.ok) address = checked.value;
    else issues.push(checked.error);
  }
  const model = input.model.trim();
  if (model === "" && input.backend !== "llama") {
    issues.push({ field: "model", message: "Enter the model's name." });
  }
  const key = input.key.trim();
  if (input.backend === "anthropic") {
    if (key === "") {
      issues.push({ field: "key", message: "Enter your Anthropic key." });
    } else if (!ANTHROPIC_KEY.test(key)) {
      issues.push({
        field: "key",
        message: "That is not an Anthropic key: one starts with sk-ant-.",
      });
    }
  }
  if (issues.length > 0) return err(issues);
  return ok({ backend: input.backend, address, model, key });
}

/** What was stored, or the built-in scan when it is not a choice. */
export function readModelSettings(stored: unknown): ModelSettings {
  if (typeof stored !== "object" || stored === null) return BUILT_IN;
  const raw = stored as Partial<Record<keyof ModelSettings, unknown>>;
  const backend = BACKENDS.find((known) => known.id === raw.backend)?.id;
  if (
    backend === undefined ||
    typeof raw.address !== "string" ||
    typeof raw.model !== "string" ||
    typeof raw.key !== "string"
  ) {
    return BUILT_IN;
  }
  return { backend, address: raw.address, model: raw.model, key: raw.key };
}

/** The host permission the model needs, as a match pattern; none built in. */
export function modelHostPattern(settings: ModelSettings): string | undefined {
  if (settings.backend === "built-in") return undefined;
  const url = new URL(settings.address);
  return `${url.protocol}//${url.hostname}/*`;
}

/**
 * One of the user's own models, saved under a name of their choosing
 * (#183). Never the built-in scan, which needs no set-up.
 */
export interface ModelSetup extends ModelSettings {
  readonly id: string;
  readonly name: string;
}

/** The set-up's fields before it is saved, which gives it an id. */
export type UnsavedSetup = Omit<ModelSetup, "id"> & { readonly id?: string };

/**
 * Every set-up, and which one *Ask the model* uses: `chosen` is a set-up's
 * id, or undefined for the built-in scan.
 */
export interface ModelChoices {
  readonly setups: readonly ModelSetup[];
  readonly chosen: string | undefined;
}

export const NO_CHOICES: ModelChoices = { setups: [], chosen: undefined };

const WHERE: Readonly<Record<Exclude<ModelBackend, "built-in">, string>> = {
  mlx: "MLX",
  llama: "llama.cpp",
  anthropic: "Anthropic",
};

/** A first name for a set-up: `Qwen3-8B-4bit on MLX`, or `llama.cpp`. */
export function suggestName(settings: ModelSettings): string {
  if (settings.backend === "built-in") return "Built in";
  const where = WHERE[settings.backend];
  const model = settings.model.trim().split("/").at(-1) ?? "";
  return model === "" ? where : `${model} on ${where}`;
}

/** The one model saved before #183, as the first set-up and the default. */
export function choicesFrom(settings: ModelSettings): ModelChoices {
  if (settings.backend === "built-in") return NO_CHOICES;
  return {
    setups: [{ ...settings, id: "1", name: suggestName(settings) }],
    chosen: "1",
  };
}

function readSetup(stored: unknown): ModelSetup | undefined {
  if (typeof stored !== "object" || stored === null) return undefined;
  const raw = stored as Partial<Record<keyof ModelSetup, unknown>>;
  const settings = readModelSettings(stored);
  if (
    settings.backend === "built-in" ||
    typeof raw.id !== "string" ||
    typeof raw.name !== "string"
  ) {
    return undefined;
  }
  return { ...settings, id: raw.id, name: raw.name };
}

/** What was stored: the set-ups, or the single model saved before them. */
export function readModelChoices(stored: unknown): ModelChoices {
  if (typeof stored !== "object" || stored === null) return NO_CHOICES;
  const raw = stored as { setups?: unknown; chosen?: unknown };
  if (!Array.isArray(raw.setups)) {
    return choicesFrom(readModelSettings(stored));
  }
  const setups = raw.setups.flatMap((one: unknown) => {
    const setup = readSetup(one);
    return setup === undefined ? [] : [setup];
  });
  const chosen = setups.some((setup) => setup.id === raw.chosen)
    ? (raw.chosen as string)
    : undefined;
  return { setups, chosen };
}

/** The set-up *Ask the model* uses; undefined for the built-in scan. */
export function chosenSetup(choices: ModelChoices): ModelSetup | undefined {
  return choices.setups.find((setup) => setup.id === choices.chosen);
}

/** What the model's adapters need: the default set-up, or the built-in scan. */
export function chosenSettings(choices: ModelChoices): ModelSettings {
  const setup = chosenSetup(choices);
  if (setup === undefined) return BUILT_IN;
  const { backend, address, model, key } = setup;
  return { backend, address, model, key };
}

/**
 * Add a set-up, with the next id, or change one in its place. The first
 * set-up becomes the default; later ones wait to be picked.
 */
export function saveSetup(
  choices: ModelChoices,
  setup: UnsavedSetup,
): ModelChoices {
  if (setup.id !== undefined) {
    const id = setup.id;
    return {
      ...choices,
      setups: choices.setups.map((one) =>
        one.id === id ? { ...setup, id } : one,
      ),
    };
  }
  const id = String(
    Math.max(0, ...choices.setups.map((one) => Number(one.id) || 0)) + 1,
  );
  return {
    setups: [...choices.setups, { ...setup, id }],
    chosen: choices.setups.length === 0 ? id : choices.chosen,
  };
}

/** Remove a set-up; the built-in scan is the default if it was. */
export function removeSetup(choices: ModelChoices, id: string): ModelChoices {
  return {
    setups: choices.setups.filter((setup) => setup.id !== id),
    chosen: choices.chosen === id ? undefined : choices.chosen,
  };
}

/** Make a set-up the default, or the built-in scan with undefined. */
export function chooseSetup(
  choices: ModelChoices,
  id: string | undefined,
): ModelChoices {
  if (id !== undefined && !choices.setups.some((setup) => setup.id === id)) {
    return choices;
  }
  return { ...choices, chosen: id };
}

/** A set-up's name is needed, and unlike the others' ignoring case. */
export function checkSetupName({
  name,
  choices,
  id,
}: {
  name: string;
  choices: ModelChoices;
  id?: string;
}): string | undefined {
  const typed = name.trim().toLowerCase();
  if (typed === "") return "Give the set-up a name.";
  const taken = choices.setups.some(
    (setup) => setup.id !== id && setup.name.trim().toLowerCase() === typed,
  );
  return taken ? "Another set-up has that name." : undefined;
}
