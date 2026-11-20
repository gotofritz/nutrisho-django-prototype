import { describe, expect, it, vi } from "vitest";

import {
  apiExample,
  apiExampleNames,
  type ApiExample,
} from "../../tests/support/api-examples";

import {
  VOCABULARY_PATH,
  createNutrishoClient,
  type FetchLike,
} from "./client";

/** The key the server's examples are signed in with. */
const EXAMPLE_KEY = "nsh_example-key-for-the-api-examples";
const SERVER = "http://localhost:8987";

/** A server that answers every request with the example's reply. */
function replying(example: ApiExample) {
  return vi.fn<FetchLike>(
    async () =>
      new Response(JSON.stringify(example.response.body), {
        status: example.response.status,
        headers: { "Content-Type": "application/json" },
      }),
  );
}

function client(
  fetch: FetchLike,
  overrides: {
    apiKey?: string;
    granted?: boolean;
    timeoutMs?: number;
  } = {},
) {
  return createNutrishoClient({
    fetch,
    loadSettings: async () => ({
      serverUrl: SERVER,
      apiKey: overrides.apiKey ?? EXAMPLE_KEY,
    }),
    hasHostPermission: async () => overrides.granted ?? true,
    ...(overrides.timeoutMs === undefined
      ? {}
      : { timeoutMs: overrides.timeoutMs }),
  });
}

function sent(fetch: ReturnType<typeof vi.fn<FetchLike>>) {
  const [url, init] = fetch.mock.calls[0]!;
  return { url: String(url), init: init ?? {} };
}

describe("the lists call", () => {
  const example = apiExample("vocabulary.json");

  it("sends the request the server's example shows", async () => {
    const fetch = replying(example);

    await client(fetch).vocabulary();

    const { url, init } = sent(fetch);
    expect(init.method).toBe(example.request.method);
    expect(url).toBe(`${SERVER}${example.request.path}`);
    expect(new Headers(init.headers).get("Authorization")).toBe(
      example.request.headers.Authorization,
    );
  });

  // The endpoints are signed in by an API key only, never the session, which
  // is what makes them safe to call from another origin (AGENTS.md).
  it("never sends the browser's cookies", async () => {
    const fetch = replying(example);

    await client(fetch).vocabulary();

    expect(sent(fetch).init.credentials).toBe("omit");
  });

  it("reads the example's reply as the user's lists", async () => {
    const lists = await client(replying(example)).vocabulary();

    expect(lists.ok && lists.value.user).toBe("cook");
    expect(lists.ok && lists.value.units.map((unit) => unit.name)).toEqual([
      "g",
      "punnet",
      "tbsp",
    ]);
  });

  it("is a 401 with the server's own reason when the key is refused", async () => {
    const refused = apiExample("vocabulary-without-key.json");

    expect(await client(replying(refused)).vocabulary()).toEqual({
      ok: false,
      error: {
        kind: "unauthorised",
        status: 401,
        message: (refused.response.body as { error: string }).error,
      },
    });
  });

  it.each(
    apiExampleNames()
      .map((name) => [name, apiExample(name)] as const)
      .filter(([, it]) => it.request.path.startsWith(VOCABULARY_PATH)),
  )("handles every reply the server's examples show: %s", async (_, it) => {
    const lists = await client(replying(it)).vocabulary();

    expect(lists.ok).toBe(it.response.status === 200);
  });
});

describe("before anything is sent", () => {
  it("asks for a key when none is saved", async () => {
    const fetch = replying(apiExample("vocabulary.json"));

    const lists = await client(fetch, { apiKey: "" }).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("no-key");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("asks for the host permission when it is not granted", async () => {
    const fetch = replying(apiExample("vocabulary.json"));

    const lists = await client(fetch, { granted: false }).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("permission-missing");
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("a server that does not answer properly", () => {
  it("is unreachable when nothing listens at the address", async () => {
    const fetch = vi.fn<FetchLike>(async () => {
      throw new TypeError("NetworkError when attempting to fetch resource.");
    });

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("unreachable");
  });

  it("gives up after the timeout", async () => {
    const fetch = vi.fn<FetchLike>(
      (_, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );

    const lists = await client(fetch, { timeoutMs: 5 }).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("timeout");
  });

  it("is a server error, with its status, for any other failure", async () => {
    const fetch = vi.fn<FetchLike>(
      async () => new Response("<h1>Server Error</h1>", { status: 500 }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error).toEqual(
      expect.objectContaining({ kind: "server-error", status: 500 }),
    );
  });

  it("is malformed when a success is not JSON", async () => {
    const fetch = vi.fn<FetchLike>(
      async () => new Response("<html>login</html>", { status: 200 }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("malformed-response");
  });

  it("is malformed when a success is not the lists", async () => {
    const fetch = vi.fn<FetchLike>(
      async () =>
        new Response(JSON.stringify({ recipes: [] }), { status: 200 }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("malformed-response");
  });
});
