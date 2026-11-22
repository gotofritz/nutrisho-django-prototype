import { describe, expect, it, vi } from "vitest";

import { MODEL_INSTRUCTION, rowsSchema } from "@/core/model-answer";
import { STEPS_INSTRUCTION, STEPS_SCHEMA } from "@/core/model-steps";
import type { FetchLike } from "@/nutrisho/client";

import { ANTHROPIC_ADDRESS } from "@/core/model-settings";

import {
  ANTHROPIC_DEFAULT_MODEL,
  createAnthropicModel,
  type AnthropicSettings,
} from "./anthropic";

const SETTINGS: AnthropicSettings = {
  model: "claude-haiku-5-5",
  key: "sk-ant-user-key",
};

const ROWS = { rows: [{ quantity: "2", ingredient: "eggs" }] };

function replying(status: number, body: unknown) {
  return vi.fn<FetchLike>(
    async () =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
      }),
  );
}

/** A message whose one block is the forced tool call. */
function toolCall(input: unknown, name = "rows") {
  return {
    type: "message",
    role: "assistant",
    content: [{ type: "tool_use", id: "toolu_1", name, input }],
    stop_reason: "tool_use",
  };
}

function model(
  fetch: FetchLike,
  overrides: {
    settings?: AnthropicSettings | undefined;
    allowed?: boolean;
    timeoutMs?: number;
  } = {},
) {
  return createAnthropicModel({
    fetch,
    loadSettings: async () =>
      "settings" in overrides ? overrides.settings : SETTINGS,
    hasHostPermission: async () => overrides.allowed ?? true,
    ...(overrides.timeoutMs === undefined
      ? {}
      : { timeoutMs: overrides.timeoutMs }),
  });
}

// Plan 012, M13 (#181): Claude, with the user's own key.
describe("createAnthropicModel", () => {
  it("starts from Haiku, at Anthropic's address", () => {
    expect(ANTHROPIC_ADDRESS).toBe("https://api.anthropic.com");
    expect(ANTHROPIC_DEFAULT_MODEL).toBe("claude-haiku-5-5");
  });

  it("forces the rows tool, and answers with its input", async () => {
    const fetch = replying(200, toolCall(ROWS));

    const answer = await model(fetch).splitLines(["2 eggs", "1 lemon"]);

    expect(answer).toEqual({ ok: true, value: ROWS });
    const [url, init] = fetch.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(url).toBe("https://api.anthropic.com/v1/messages");
    expect(init?.credentials).toBe("omit");
    expect(headers.get("x-api-key")).toBe("sk-ant-user-key");
    expect(headers.get("anthropic-version")).toBe("2023-06-01");
    expect(headers.get("anthropic-dangerous-direct-browser-access")).toBe(
      "true",
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      model: "claude-haiku-5-5",
      max_tokens: 4096,
      system: MODEL_INSTRUCTION,
      tools: [
        {
          name: "rows",
          description: "The rows, one per line, in order.",
          input_schema: rowsSchema(2),
        },
      ],
      tool_choice: { type: "tool", name: "rows" },
      messages: [
        {
          role: "user",
          content: '[{"line":1,"text":"2 eggs"},{"line":2,"text":"1 lemon"}]',
        },
      ],
    });
  });

  it("forces the steps tool to rewrite the steps", async () => {
    const STEPS = { steps: [{ title: "", text: "Fry" }] };
    const fetch = replying(200, toolCall(STEPS, "steps"));

    const answer = await model(fetch).rewriteSteps([
      { title: "", text: "Fry it all" },
    ]);

    expect(answer).toEqual({ ok: true, value: STEPS });
    const body = JSON.parse(String(fetch.mock.calls[0]?.[1]?.body)) as Record<
      string,
      unknown
    >;
    expect(body).toMatchObject({
      system: STEPS_INSTRUCTION,
      tools: [
        {
          name: "steps",
          description: "The steps, rewritten, in order.",
          input_schema: STEPS_SCHEMA,
        },
      ],
      tool_choice: { type: "tool", name: "steps" },
      messages: [
        { role: "user", content: '[{"title":"","text":"Fry it all"}]' },
      ],
    });
  });

  it("does not take one tool's answer for the other's", async () => {
    const fetch = replying(200, toolCall(ROWS, "rows"));

    const answer = await model(fetch).rewriteSteps([
      { title: "", text: "Fry" },
    ]);

    expect(answer.ok || answer.error.kind).toBe("malformed-response");
  });

  it.each([
    ["no model is set up", undefined],
    ["no key is saved", { ...SETTINGS, key: "" }],
  ])("sends nothing when %s", async (_, settings) => {
    const fetch = replying(200, toolCall(ROWS));

    const answer = await model(fetch, { settings }).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("not-set-up");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends nothing before it is allowed to reach Anthropic", async () => {
    const fetch = replying(200, toolCall(ROWS));

    const answer = await model(fetch, { allowed: false }).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("permission-missing");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    [401, "authentication_error", "unauthorised"],
    [403, "permission_error", "unauthorised"],
    [404, "not_found_error", "unknown-model"],
    [429, "rate_limit_error", "rate-limited"],
    [529, "overloaded_error", "server-error"],
  ])(
    "reads a %i (%s) as %s, in Anthropic's words",
    async (status, type, kind) => {
      const answer = await model(
        replying(status, {
          type: "error",
          error: { type, message: "said Anthropic" },
        }),
      ).splitLines(["x"]);

      expect(answer).toEqual({
        ok: false,
        error: { kind, message: "said Anthropic", status },
      });
    },
  );

  it.each([
    [
      "a reply with no tool call",
      { type: "message", content: [{ type: "text", text: "Hi" }] },
    ],
    ["a body that is not JSON", "<html>"],
  ])("refuses %s", async (_, body) => {
    const answer = await model(replying(200, body)).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("malformed-response");
  });

  it("says when nothing answered", async () => {
    const answer = await model(
      vi.fn<FetchLike>(async () => {
        throw new TypeError("NetworkError when attempting to fetch resource.");
      }),
    ).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("unreachable");
  });

  // #182: a check costs nothing, sends no recipe, and finds a wrong model.
  it("checks the key and the model by looking the model up", async () => {
    const fetch = replying(200, { type: "model", id: "claude-haiku-5-5" });

    const checked = await model(fetch).check();

    expect(checked).toEqual({ ok: true, value: undefined });
    const [url, init] = fetch.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(url).toBe("https://api.anthropic.com/v1/models/claude-haiku-5-5");
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(headers.get("x-api-key")).toBe("sk-ant-user-key");
    expect(headers.get("anthropic-dangerous-direct-browser-access")).toBe(
      "true",
    );
  });

  it("says when the model checked is not there", async () => {
    const checked = await model(
      replying(404, {
        type: "error",
        error: { type: "not_found_error", message: "model: nope" },
      }),
    ).check();

    expect(checked).toMatchObject({
      ok: false,
      error: { kind: "unknown-model", message: "model: nope" },
    });
  });
});
