import { describe, expect, it, vi } from "vitest";

import { MODEL_INSTRUCTION, rowsSchema } from "@/core/model-answer";
import { STEPS_INSTRUCTION, STEPS_SCHEMA } from "@/core/model-steps";
import type { FetchLike } from "@/nutrisho/client";

import {
  LLAMA_DEFAULTS,
  MLX_DEFAULTS,
  createOpenAiCompatibleModel,
  type LocalModelSettings,
} from "./openai-compatible";

const SETTINGS: LocalModelSettings = {
  address: "http://localhost:8080",
  model: "mlx-community/Qwen3-8B-4bit",
  key: "",
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

/** A chat completion, as both servers answer one that is not streamed. */
function completion(content: string) {
  return {
    object: "chat.completion",
    choices: [{ index: 0, message: { role: "assistant", content } }],
  };
}

function model(
  fetch: FetchLike,
  overrides: {
    settings?: LocalModelSettings | undefined;
    allowed?: boolean;
    timeoutMs?: number;
  } = {},
) {
  return createOpenAiCompatibleModel({
    fetch,
    loadSettings: async () =>
      "settings" in overrides ? overrides.settings : SETTINGS,
    hasHostPermission: async () => overrides.allowed ?? true,
    ...(overrides.timeoutMs === undefined
      ? {}
      : { timeoutMs: overrides.timeoutMs }),
  });
}

function sent(fetch: ReturnType<typeof replying>) {
  const [url, init] = fetch.mock.calls[0]!;
  return {
    url,
    init,
    body: JSON.parse(String(init?.body)) as Record<string, unknown>,
    headers: new Headers(init?.headers),
  };
}

// Plan 012, M13 (#181): MLX and llama.cpp, on the user's own machine, both
// behind the OpenAI-compatible API, as timbuktu runs them.
describe("createOpenAiCompatibleModel", () => {
  it("starts from timbuktu's addresses", () => {
    expect(MLX_DEFAULTS.address).toBe("http://localhost:8080");
    expect(LLAMA_DEFAULTS.address).toBe("http://localhost:8081");
  });

  it("asks for the rows in the schema's shape, and answers with them", async () => {
    const fetch = replying(200, completion(JSON.stringify(ROWS)));

    const answer = await model(fetch).splitLines(["2 eggs", "1 lemon"]);

    expect(answer).toEqual({ ok: true, value: ROWS });
    const { url, init, body, headers } = sent(fetch);
    expect(url).toBe("http://localhost:8080/v1/chat/completions");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("omit");
    expect(headers.has("Authorization")).toBe(false);
    expect(body).toEqual({
      model: "mlx-community/Qwen3-8B-4bit",
      stream: false,
      temperature: 0,
      // Thinking is no help in splitting a line, and can use up the room.
      chat_template_kwargs: { enable_thinking: false },
      response_format: {
        type: "json_schema",
        json_schema: { name: "rows", schema: rowsSchema(2) },
      },
      messages: [
        { role: "system", content: MODEL_INSTRUCTION },
        {
          role: "user",
          content: '[{"line":1,"text":"2 eggs"},{"line":2,"text":"1 lemon"}]',
        },
      ],
    });
  });

  it("asks for the steps rewritten, in their schema's shape", async () => {
    const STEPS = { steps: [{ title: "", text: "Fry" }] };
    const fetch = replying(200, completion(JSON.stringify(STEPS)));

    const answer = await model(fetch).rewriteSteps([
      { title: "", text: "Fry it all" },
    ]);

    expect(answer).toEqual({ ok: true, value: STEPS });
    const { body } = sent(fetch);
    expect(body.response_format).toEqual({
      type: "json_schema",
      json_schema: { name: "steps", schema: STEPS_SCHEMA },
    });
    expect(body.messages).toEqual([
      { role: "system", content: STEPS_INSTRUCTION },
      { role: "user", content: '[{"title":"","text":"Fry it all"}]' },
    ]);
  });

  it("leaves the model out when none is named, as llama.cpp allows", async () => {
    const fetch = replying(200, completion(JSON.stringify(ROWS)));

    await model(fetch, { settings: { ...SETTINGS, model: "" } }).splitLines([
      "x",
    ]);

    expect(sent(fetch).body).not.toHaveProperty("model");
  });

  it("sends the server's own key, when it has one, as a Bearer token", async () => {
    const fetch = replying(200, completion(JSON.stringify(ROWS)));

    await model(fetch, {
      settings: { ...SETTINGS, key: "local-key" },
    }).splitLines(["x"]);

    expect(sent(fetch).headers.get("Authorization")).toBe("Bearer local-key");
  });

  // Qwen3 thinks aloud first, and some models fence their JSON.
  it.each([
    ["thinking first", `<think>Two eggs.</think>\n${JSON.stringify(ROWS)}`],
    ["a fence", "```json\n" + JSON.stringify(ROWS) + "\n```"],
  ])("reads the JSON past %s", async (_, content) => {
    const answer = await model(replying(200, completion(content))).splitLines([
      "2 eggs",
    ]);

    expect(answer).toEqual({ ok: true, value: ROWS });
  });

  it("sends nothing when no model is set up", async () => {
    const fetch = replying(200, completion("{}"));

    const answer = await model(fetch, { settings: undefined }).splitLines([
      "x",
    ]);

    expect(answer).toEqual({
      ok: false,
      error: { kind: "not-set-up", message: "no model is set up" },
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends nothing to an address it was not allowed to reach", async () => {
    const fetch = replying(200, completion("{}"));

    const answer = await model(fetch, { allowed: false }).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("permission-missing");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    [401, "unauthorised"],
    [403, "unauthorised"],
    [429, "rate-limited"],
    [500, "server-error"],
  ])("reads a %i as %s, in the server's own words", async (status, kind) => {
    const answer = await model(
      replying(status, { error: { message: "said the server" } }),
    ).splitLines(["x"]);

    expect(answer).toEqual({
      ok: false,
      error: { kind, message: "said the server", status },
    });
  });

  it("says when the model named is not there", async () => {
    const answer = await model(
      replying(404, { error: { message: "model 'qwen' not found" } }),
    ).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("unknown-model");
  });

  it("says when the address has no chat endpoint", async () => {
    const answer = await model(replying(404, "Not Found")).splitLines(["x"]);

    expect(answer).toEqual({
      ok: false,
      error: {
        kind: "server-error",
        message: "nothing at /v1/chat/completions: the server answered 404",
        status: 404,
      },
    });
  });

  it.each([
    ["a reply that is not a completion", { done: true }],
    ["content that is not JSON", completion("Here are your rows:")],
    ["a body that is not JSON", "<html>"],
  ])("refuses %s", async (_, body) => {
    const answer = await model(replying(200, body)).splitLines(["x"]);

    expect(answer.ok || answer.error.kind).toBe("malformed-response");
  });

  // Seen by hand (#182): llama.cpp with Qwen3 answered a group with no
  // content, its thinking having used up the room.
  it("says when the model ran out of room before it answered", async () => {
    const answer = await model(
      replying(200, {
        choices: [
          {
            finish_reason: "length",
            message: {
              role: "assistant",
              content: null,
              reasoning_content: "Okay, let me split these lines…",
            },
          },
        ],
      }),
    ).splitLines(["x"]);

    expect(answer).toEqual({
      ok: false,
      error: {
        kind: "malformed-response",
        message:
          "the model ran out of room before it answered, thinking (finish_reason: length)",
      },
    });
  });

  it("says why a completion holds no answer", async () => {
    const answer = await model(
      replying(200, {
        choices: [
          {
            finish_reason: "stop",
            message: { role: "assistant", content: null },
          },
        ],
      }),
    ).splitLines(["x"]);

    expect(answer.ok || answer.error.message).toBe(
      "the server's reply holds no answer (finish_reason: stop)",
    );
  });

  it("reads content sent as parts", async () => {
    const answer = await model(
      replying(200, {
        choices: [
          {
            message: {
              role: "assistant",
              content: [{ type: "text", text: JSON.stringify(ROWS) }],
            },
          },
        ],
      }),
    ).splitLines(["x"]);

    expect(answer).toEqual({ ok: true, value: ROWS });
  });

  it("says when nothing answered", async () => {
    const answer = await model(
      vi.fn<FetchLike>(async () => {
        throw new TypeError("NetworkError when attempting to fetch resource.");
      }),
    ).splitLines(["x"]);

    expect(answer).toEqual({
      ok: false,
      error: {
        kind: "unreachable",
        message: "NetworkError when attempting to fetch resource.",
      },
    });
  });

  it("gives up after its time, and says so", async () => {
    const hanging = vi.fn<FetchLike>(
      (_, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );

    const answer = await model(hanging, { timeoutMs: 5 }).splitLines(["x"]);

    expect(answer).toEqual({
      ok: false,
      error: { kind: "timeout", message: "no answer within 0.005s" },
    });
  });

  // #182: the log showed nothing of the model until it was asked.
  it("checks the server by listing its models, sending nothing else", async () => {
    const fetch = replying(200, { object: "list", data: [] });

    const checked = await model(fetch, {
      settings: { ...SETTINGS, key: "local-key" },
    }).check();

    expect(checked).toEqual({ ok: true, value: undefined });
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("http://localhost:8080/v1/models");
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer local-key",
    );
  });

  it("says why a check fails", async () => {
    const unreachable = vi.fn<FetchLike>(async () => {
      throw new TypeError("NetworkError when attempting to fetch resource.");
    });

    expect(
      (await model(unreachable).check()).ok ||
        (await model(unreachable).check()),
    ).toMatchObject({ ok: false, error: { kind: "unreachable" } });
    expect(
      await model(replying(401, { error: "bad key" })).check(),
    ).toMatchObject({ ok: false, error: { kind: "unauthorised" } });
    expect(
      await model(replying(200, {}), { allowed: false }).check(),
    ).toMatchObject({ ok: false, error: { kind: "permission-missing" } });
  });
});
