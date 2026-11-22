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
