import { MODEL_INSTRUCTION, numbered, rowsSchema } from "@/core/model-answer";
import { STEPS_INSTRUCTION, STEPS_SCHEMA } from "@/core/model-steps";
import { ANTHROPIC_ADDRESS } from "@/core/model-settings";
import type { LineModel, ModelError } from "@/core/ports/types";
import { ok, type Result } from "@/core/result";
import type { FetchLike } from "@/nutrisho/client";

import {
  CHECK_TIMEOUT_MS,
  failure,
  get,
  jsonOf,
  messageOf,
  post,
} from "./model-request";

/**
 * Claude, with the user's own key (plan 012, M13, D20): the Messages API,
 * with a tool whose input schema is the answer's and which the model must
 * call. Only the lines, or the steps, are sent, with a fixed instruction. The opt-in
 * header lets a request from the extension's page through; the key lives
 * in the extension's storage, never in a web page.
 */
export interface AnthropicSettings {
  /** A current Claude model id. */
  readonly model: string;
  /** The user's own key, from the Anthropic Console. */
  readonly key: string;
}

/** Splitting short lines needs a quick, cheap model. */
export const ANTHROPIC_DEFAULT_MODEL = "claude-haiku-5-5";

export interface AnthropicDeps {
  readonly fetch: FetchLike;
  /** Undefined while no model is set up; read on every call. */
  readonly loadSettings: () => Promise<AnthropicSettings | undefined>;
  readonly hasHostPermission: (address: string) => Promise<boolean>;
  readonly timeoutMs?: number;
}

export const ANTHROPIC_TIMEOUT_MS = 30_000;

const MESSAGES_PATH = "/v1/messages";

function kindOf(status: number): ModelError["kind"] {
  if (status === 401 || status === 403) return "unauthorised";
  if (status === 404) return "unknown-model";
  if (status === 429) return "rate-limited";
  return "server-error";
}

/** The forced tool call's input: the model's answer. */
function answerOf(body: unknown, tool: string): Result<unknown, ModelError> {
  const content =
    typeof body === "object" && body !== null
      ? (body as { content?: unknown }).content
      : undefined;
  const call = Array.isArray(content)
    ? (content as { type?: unknown; name?: unknown; input?: unknown }[]).find(
        (block) => block.type === "tool_use" && block.name === tool,
      )
    : undefined;
  return call === undefined
    ? failure("malformed-response", `Claude's reply holds no ${tool}`)
    : ok(call.input);
}

/** One thing to ask: its tool, what the model is told, the shape, the input. */
interface Task {
  readonly tool: string;
  readonly description: string;
  readonly instruction: string;
  readonly schema: object;
  readonly input: unknown;
}

export function createAnthropicModel(deps: AnthropicDeps): LineModel {
  const timeoutMs = deps.timeoutMs ?? ANTHROPIC_TIMEOUT_MS;

  /** The settings, once a key is saved and Anthropic may be reached. */
  async function ready(): Promise<Result<AnthropicSettings, ModelError>> {
    const settings = await deps.loadSettings();
    if (settings === undefined) {
      return failure("not-set-up", "no model is set up");
    }
    if (settings.key === "") {
      return failure("not-set-up", "no Anthropic key is saved");
    }
    if (!(await deps.hasHostPermission(ANTHROPIC_ADDRESS))) {
      return failure(
        "permission-missing",
        `the clipper has not been allowed to reach ${ANTHROPIC_ADDRESS}`,
      );
    }
    return ok(settings);
  }

  function headersFor(settings: AnthropicSettings): Record<string, string> {
    return {
      "x-api-key": settings.key,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    };
  }

  function refusal(
    response: Response,
    body: unknown,
  ): Result<never, ModelError> {
    return failure(
      kindOf(response.status),
      messageOf(body) ??
        `Anthropic answered ${response.status} ${response.statusText}`.trim(),
      response.status,
    );
  }

  async function ask(task: Task): Promise<Result<unknown, ModelError>> {
    const settings = await ready();
    if (!settings.ok) return settings;
    const reply = await post(
      deps.fetch,
      `${ANTHROPIC_ADDRESS}${MESSAGES_PATH}`,
      headersFor(settings.value),
      {
        model: settings.value.model,
        max_tokens: 4096,
        system: task.instruction,
        tools: [
          {
            name: task.tool,
            description: task.description,
            input_schema: task.schema,
          },
        ],
        tool_choice: { type: "tool", name: task.tool },
        messages: [{ role: "user", content: JSON.stringify(task.input) }],
      },
      timeoutMs,
    );
    if (!reply.ok) return reply;
    const body = await jsonOf(reply.value);
    return reply.value.ok
      ? answerOf(body, task.tool)
      : refusal(reply.value, body);
  }

  return {
    splitLines: (lines) =>
      ask({
        tool: "rows",
        description: "The rows, one per line, in order.",
        instruction: MODEL_INSTRUCTION,
        schema: rowsSchema(lines.length),
        input: numbered(lines),
      }),
    rewriteSteps: (steps) =>
      ask({
        tool: "steps",
        description: "The steps, rewritten, in order.",
        instruction: STEPS_INSTRUCTION,
        schema: STEPS_SCHEMA,
        input: steps,
      }),
    /** Looking the model up checks the key and the model's name, for free. */
    async check() {
      const settings = await ready();
      if (!settings.ok) return settings;
      const reply = await get(
        deps.fetch,
        `${ANTHROPIC_ADDRESS}/v1/models/${encodeURIComponent(settings.value.model)}`,
        headersFor(settings.value),
        CHECK_TIMEOUT_MS,
      );
      if (!reply.ok) return reply;
      return reply.value.ok
        ? ok(undefined)
        : refusal(reply.value, await jsonOf(reply.value));
    },
  };
}
