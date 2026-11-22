import { describe, expect, it, vi } from "vitest";

import {
  BUILT_IN,
  defaultsFor,
  type ModelSettings,
} from "@/core/model-settings";
import type { FetchLike } from "@/nutrisho/client";

import { createUserModel } from "./user-model";

const ROWS = { rows: [{ quantity: "2", ingredient: "eggs" }] };

/** A server that answers as both kinds would. */
function anyServer() {
  return vi.fn<FetchLike>(
    async () =>
      new Response(
        JSON.stringify({
          choices: [{ message: { content: JSON.stringify(ROWS) } }],
          content: [
            { type: "tool_use", name: "rows", input: ROWS },
            { type: "tool_use", name: "steps", input: ROWS },
          ],
        }),
      ),
  );
}

function model(fetch: FetchLike, settings: ModelSettings) {
  return createUserModel({
    fetch,
    loadSettings: async () => settings,
    hasHostPermission: async () => true,
  });
}

// Plan 012, M13 (#181): the backend saved on the options page, read on
// every call, so a change there takes effect at once.
describe("createUserModel", () => {
  it.each([
    ["mlx", "http://localhost:8080/v1/chat/completions"],
    ["llama", "http://localhost:8081/v1/chat/completions"],
    ["anthropic", "https://api.anthropic.com/v1/messages"],
  ] as const)("asks %s at its own address", async (backend, url) => {
    const fetch = anyServer();

    const answer = await model(fetch, {
      ...defaultsFor(backend),
      key: "sk-ant-api03-clipper",
    }).splitLines(["2 eggs"]);

    expect(answer).toEqual({ ok: true, value: ROWS });
    expect(fetch.mock.calls[0]?.[0]).toBe(url);
  });

  it("asks nothing while the built-in scan is chosen", async () => {
    const fetch = anyServer();

    const answer = await model(fetch, BUILT_IN).splitLines(["2 eggs"]);

    expect(answer.ok || answer.error.kind).toBe("not-set-up");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["mlx", "llama", "anthropic"] as const)(
    "asks %s to rewrite the steps",
    async (backend) => {
      const fetch = anyServer();

      const answer = await model(fetch, {
        ...defaultsFor(backend),
        key: "sk-ant-api03-clipper",
      }).rewriteSteps([{ title: "", text: "Fry" }]);

      expect(answer).toEqual({ ok: true, value: ROWS });
    },
  );

  it("rewrites nothing while the built-in scan is chosen", async () => {
    const fetch = anyServer();

    const answer = await model(fetch, BUILT_IN).rewriteSteps([
      { title: "", text: "Fry" },
    ]);

    expect(answer.ok || answer.error.kind).toBe("not-set-up");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    ["mlx", "http://localhost:8080/v1/models"],
    ["anthropic", "https://api.anthropic.com/v1/models/claude-haiku-5-5"],
  ] as const)("checks %s at its own address", async (backend, url) => {
    const fetch = anyServer();

    const checked = await model(fetch, {
      ...defaultsFor(backend),
      key: "sk-ant-api03-clipper",
    }).check();

    expect(checked.ok).toBe(true);
    expect(fetch.mock.calls[0]?.[0]).toBe(url);
  });

  it("checks nothing while the built-in scan is chosen", async () => {
    const fetch = anyServer();

    const checked = await model(fetch, BUILT_IN).check();

    expect(checked.ok || checked.error.kind).toBe("not-set-up");
    expect(fetch).not.toHaveBeenCalled();
  });
});
