import { MODEL_INSTRUCTION, numbered, rowsSchema } from "@/core/model-answer";
import { STEPS_INSTRUCTION, STEPS_SCHEMA } from "@/core/model-steps";
import type { LineModel, ModelError } from "@/core/ports/types";
import { ok, type Result } from "@/core/result";
import type { FetchLike } from "@/nutrisho/client";

import {
  CHECK_TIMEOUT_MS,
  failure,
  get,
  jsonIn,
  jsonOf,
  messageOf,
  post,
} from "./model-request";

/**
 * MLX and llama.cpp on the user's own machine (plan 012, M13, D20), as
 * timbuktu runs them: both behind the OpenAI-compatible
 * `/v1/chat/completions`, not streamed, with the rows' JSON schema as
 * `response_format`. Only the lines, or the steps, are sent, with a fixed
 * instruction.
 */
export interface LocalModelSettings {
  /** Where the server listens. */
  readonly address: string;
  /** The model it was started with; empty when it serves one model only. */
  readonly model: string;
  /** The server's own key, when it asks for one; empty when it does not. */
  readonly key: string;
}

/** `mlx_lm.server --model mlx-community/Qwen3-8B-4bit --port 8080` */
export const MLX_DEFAULTS: LocalModelSettings = {
  address: "http://localhost:8080",
  model: "mlx-community/Qwen3-8B-4bit",
  key: "",
};

/** `llama-server -hf unsloth/Qwen3-8B-GGUF:UD-Q4_K_XL --port 8081` */
export const LLAMA_DEFAULTS: LocalModelSettings = {
  address: "http://localhost:8081",
  model: "",
  key: "",
};

export interface LocalModelDeps {
  readonly fetch: FetchLike;
  /** Undefined while no model is set up; read on every call. */
  readonly loadSettings: () => Promise<LocalModelSettings | undefined>;
  readonly hasHostPermission: (address: string) => Promise<boolean>;
  readonly timeoutMs?: number;
}

/** A local model on an ordinary machine can take its time over a long group. */
export const LOCAL_TIMEOUT_MS = 60_000;

const CHAT_PATH = "/v1/chat/completions";
const MODELS_PATH = "/v1/models";

function kindOf(status: number, said: string): ModelError["kind"] {
  if (status === 401 || status === 403) return "unauthorised";
  if (status === 429) return "rate-limited";
  if (status === 404 && /model/i.test(said)) return "unknown-model";
  return "server-error";
}

interface Choice {
  readonly finish_reason?: unknown;
  readonly message?: {
    readonly content?: unknown;
    readonly reasoning_content?: unknown;
  };
}

/** The text of a message's content, whether a string or a list of parts. */
function textOf(content: unknown): string | undefined {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return undefined;
  const texts = content
    .map((part) =>
      typeof part === "object" && part !== null
        ? (part as { text?: unknown }).text
        : undefined,
    )
    .filter((text): text is string => typeof text === "string");
  return texts.length === 0 ? undefined : texts.join("");
}

/** The completion's text, then the JSON in it. */
function answerOf(body: unknown): Result<unknown, ModelError> {
  const choices =
    typeof body === "object" && body !== null
      ? (body as { choices?: unknown }).choices
      : undefined;
  const choice = Array.isArray(choices)
    ? (choices[0] as Choice | undefined)
    : undefined;
  if (choice === undefined) {
    return failure(
      "malformed-response",
      "the server's reply is not a chat completion",
    );
  }
  const content = textOf(choice.message?.content);
  if (content !== undefined && content.trim() !== "") return jsonIn(content);
  const finish =
    typeof choice.finish_reason === "string"
      ? ` (finish_reason: ${choice.finish_reason})`
      : "";
  // A thinking model can spend all its room thinking, and answer nothing.
  if (choice.finish_reason === "length") {
    const thinking =
      typeof choice.message?.reasoning_content === "string" ? ", thinking" : "";
    return failure(
      "malformed-response",
      `the model ran out of room before it answered${thinking}${finish}`,
    );
  }
  return failure(
    "malformed-response",
    `the server's reply holds no answer${finish}`,
  );
}

/** One thing to ask: its name, what the model is told, the shape, the input. */
interface Task {
  readonly name: string;
  readonly instruction: string;
  readonly schema: object;
  readonly input: unknown;
}

export function createOpenAiCompatibleModel(deps: LocalModelDeps): LineModel {
  const timeoutMs = deps.timeoutMs ?? LOCAL_TIMEOUT_MS;

  /** The settings, once a model is set up and may be reached. */
  async function ready(): Promise<Result<LocalModelSettings, ModelError>> {
    const settings = await deps.loadSettings();
    if (settings === undefined) {
      return failure("not-set-up", "no model is set up");
    }
    if (!(await deps.hasHostPermission(settings.address))) {
      return failure(
        "permission-missing",
        `the clipper has not been allowed to reach ${settings.address}`,
      );
    }
    return ok(settings);
  }

  function keyOf(settings: LocalModelSettings): Record<string, string> {
    return settings.key === ""
      ? {}
      : { Authorization: `Bearer ${settings.key}` };
  }

  /** A reply that is not a success, as the error it is. */
  function refusal(
    response: Response,
    body: unknown,
    path: string,
  ): Result<never, ModelError> {
    const said = messageOf(body);
    if (said === undefined && response.status === 404) {
      return failure(
        "server-error",
        `nothing at ${path}: the server answered 404`,
        404,
      );
    }
    const words =
      said ??
      `the server answered ${response.status} ${response.statusText}`.trim();
    return failure(kindOf(response.status, words), words, response.status);
  }

  async function ask(task: Task): Promise<Result<unknown, ModelError>> {
    const settings = await ready();
    if (!settings.ok) return settings;
    const { address, model } = settings.value;
    const reply = await post(
      deps.fetch,
      `${address}${CHAT_PATH}`,
      keyOf(settings.value),
      {
        ...(model === "" ? {} : { model }),
        stream: false,
        temperature: 0,
        // Thinking is no help in splitting a line, and can use up the room;
        // llama.cpp and MLX pass this to the chat template (Qwen3 reads it).
        chat_template_kwargs: { enable_thinking: false },
        response_format: {
          type: "json_schema",
          json_schema: { name: task.name, schema: task.schema },
        },
        messages: [
          { role: "system", content: task.instruction },
          { role: "user", content: JSON.stringify(task.input) },
        ],
      },
      timeoutMs,
    );
    if (!reply.ok) return reply;
    const body = await jsonOf(reply.value);
    return reply.value.ok
      ? answerOf(body)
      : refusal(reply.value, body, CHAT_PATH);
  }

  return {
    splitLines: (lines) =>
      ask({
        name: "rows",
        instruction: MODEL_INSTRUCTION,
        schema: rowsSchema(lines.length),
        input: numbered(lines),
      }),
    rewriteSteps: (steps) =>
      ask({
        name: "steps",
        instruction: STEPS_INSTRUCTION,
        schema: STEPS_SCHEMA,
        input: steps,
      }),
    /** Both servers list their models at `/v1/models`. */
    async check() {
      const settings = await ready();
      if (!settings.ok) return settings;
      const reply = await get(
        deps.fetch,
        `${settings.value.address}${MODELS_PATH}`,
        keyOf(settings.value),
        CHECK_TIMEOUT_MS,
      );
      if (!reply.ok) return reply;
      return reply.value.ok
        ? ok(undefined)
        : refusal(reply.value, await jsonOf(reply.value), MODELS_PATH);
    },
  };
}
