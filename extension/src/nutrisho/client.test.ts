import { describe, expect, it, vi } from "vitest";

import {
  apiExample,
  apiExampleNames,
  type ApiExample,
} from "../../tests/support/api-examples";

import { EMPTY_ROW } from "@/core/ingredient-line";
import { startDraft, type RecipeDraft } from "@/core/recipe-draft";

import {
  SAVE_PATH,
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
        headers: {
          "Content-Type": "application/json",
          ...example.response.headers,
        },
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

  // #149: an expired key has a code of its own, so the clipper can say to
  // make a new one rather than to check it.
  it("tells an expired key from a wrong one", async () => {
    const expired = apiExample("vocabulary-key-expired.json");

    expect(await client(replying(expired)).vocabulary()).toEqual({
      ok: false,
      error: {
        kind: "key-expired",
        status: 401,
        message: (expired.response.body as { error: string }).error,
      },
    });
  });

  it("says how long to wait when there were too many requests", async () => {
    const busy = apiExample("vocabulary-too-many-requests.json");
    const waiting = {
      ...busy,
      response: { ...busy.response, headers: { "Retry-After": "42" } },
    };

    const lists = await client(replying(waiting)).vocabulary();

    expect(!lists.ok && lists.error).toEqual({
      kind: "rate-limited",
      status: 429,
      message: (busy.response.body as { error: string }).error,
      retryAfter: 42,
    });
  });

  it("leaves the wait out when Retry-After is not a number of seconds", async () => {
    const lists = await client(
      replying(apiExample("vocabulary-too-many-requests.json")),
    ).vocabulary();

    expect(!lists.ok && lists.error).not.toHaveProperty("retryAfter");
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

  it("is not a Nutrisho when a success is not JSON", async () => {
    const fetch = vi.fn<FetchLike>(
      async () => new Response("<html>login</html>", { status: 200 }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("not-nutrisho");
  });

  // Plan 012, M11: something else listens at the address, or an old server
  // without the endpoint.
  it.each([404, 405])(
    "is not a Nutrisho when the endpoint is a %s",
    async (status) => {
      const fetch = vi.fn<FetchLike>(
        async () => new Response("<h1>Not Found</h1>", { status }),
      );

      const lists = await client(fetch).vocabulary();

      expect(!lists.ok && lists.error).toEqual(
        expect.objectContaining({ kind: "not-nutrisho", status }),
      );
    },
  );

  it("is not a Nutrisho when a refusal is not in the server's shape", async () => {
    const fetch = vi.fn<FetchLike>(
      async () =>
        new Response(JSON.stringify({ message: "nope" }), { status: 401 }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error.kind).toBe("not-nutrisho");
  });

  it("passes on a server error's own reason when it sends one", async () => {
    const fetch = vi.fn<FetchLike>(
      async () =>
        new Response(JSON.stringify({ error: "The database is locked." }), {
          status: 503,
        }),
    );

    const lists = await client(fetch).vocabulary();

    expect(!lists.ok && lists.error).toEqual({
      kind: "server-error",
      status: 503,
      message: "The database is locked.",
    });
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

/** The recipe every save example sends. */
const NORMA: RecipeDraft = {
  ...startDraft({
    id: "01a1f5b5-dbe2-704a-b591-7ffbcff6762e",
    title: "Pasta alla Norma",
    url: "https://example.com/norma",
    now: "2026-11-20T09:00:00.000Z",
  }),
  servings: "4",
  cuisine: "med.italy",
  tags: ["dinner"],
  steps: [
    { title: "", text: "Fry the aubergine." },
    { title: "", text: "Toss with the pasta." },
  ],
  groups: [
    {
      name: "",
      rows: [
        {
          ...EMPTY_ROW,
          quantity: "2",
          ingredient: "aubergines",
          preparation: "cubed",
        },
        { ...EMPTY_ROW, quantity: "400", unit: "g", ingredient: "rigatoni" },
        { ...EMPTY_ROW, unit: "handful", ingredient: "basil", note: "torn" },
      ],
    },
  ],
};

describe("the save", () => {
  const example = apiExample("save.json");

  it("sends the request the server's example shows", async () => {
    const fetch = replying(example);

    await client(fetch).saveRecipe(NORMA);

    const { url, init } = sent(fetch);
    const headers = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(url).toBe(`${SERVER}${example.request.path}`);
    expect(headers.get("Authorization")).toBe(
      example.request.headers.Authorization,
    );
    expect(headers.get("Content-Type")).toBe(
      example.request.headers["Content-Type"],
    );
    expect(JSON.parse(String(init.body))).toEqual(example.request.body);
    expect(init.credentials).toBe("omit");
  });

  it("answers with where the new recipe is, to open in edit mode", async () => {
    expect(await client(replying(example)).saveRecipe(NORMA)).toEqual({
      ok: true,
      value: {
        openUrl: `${SERVER}/recipes/01a1f5b5-dbe2-704a-b591-7ffbcff6762e/?edit=1`,
        name: "Pasta alla Norma",
        created: true,
        renamed: false,
        inTrash: false,
        warnings: [],
      },
    });
  });

  it("says nothing was written when the server already had the recipe", async () => {
    const saved = await client(
      replying(apiExample("save-again.json")),
    ).saveRecipe(NORMA);

    expect(saved.ok && saved.value.created).toBe(false);
  });

  it("passes the server's warnings on", async () => {
    const warned = {
      ...example,
      response: {
        ...example.response,
        body: {
          ...(example.response.body as object),
          warnings: ["handful is now one of your own units."],
        },
      },
    };

    const saved = await client(replying(warned)).saveRecipe(NORMA);

    expect(saved.ok && saved.value.warnings).toEqual([
      "handful is now one of your own units.",
    ]);
  });

  it.each(["save-refused.json", "save-id-taken.json"])(
    "is refused, in the server's own words, as %s shows",
    async (name) => {
      const refusal = apiExample(name);

      expect(await client(replying(refusal)).saveRecipe(NORMA)).toEqual({
        ok: false,
        error: {
          kind: "refused",
          status: refusal.response.status,
          message: (refusal.response.body as { error: string }).error,
        },
      });
    },
  );

  // #149: a save may bring only so many recipes and new names, and a body
  // only so large.
  it("is too large when the server says so", async () => {
    const fetch = vi.fn<FetchLike>(
      async () =>
        new Response(
          JSON.stringify({
            error:
              "One request may make at most 150 new names; this one would make 151.",
            code: "too_many_new_names",
          }),
          { status: 413 },
        ),
    );

    const saved = await client(fetch).saveRecipe(NORMA);

    expect(!saved.ok && saved.error).toEqual({
      kind: "too-large",
      status: 413,
      message:
        "One request may make at most 150 new names; this one would make 151.",
    });
  });

  it("is a server error when the server cannot read what this clipper sends", async () => {
    const saved = await client(
      replying(apiExample("save-not-json.json")),
    ).saveRecipe(NORMA);

    expect(!saved.ok && saved.error.kind).toBe("server-error");
  });

  it("is malformed when a success does not name the recipe", async () => {
    const fetch = vi.fn<FetchLike>(
      async () =>
        new Response(JSON.stringify({ recipes: [] }), { status: 201 }),
    );

    const saved = await client(fetch).saveRecipe(NORMA);

    expect(!saved.ok && saved.error.kind).toBe("malformed-response");
  });

  it("asks for a key before sending anything", async () => {
    const fetch = replying(example);

    const saved = await client(fetch, { apiKey: "" }).saveRecipe(NORMA);

    expect(!saved.ok && saved.error.kind).toBe("no-key");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(
    apiExampleNames()
      .map((name) => [name, apiExample(name)] as const)
      .filter(([, it]) => it.request.path.startsWith(SAVE_PATH)),
  )("handles every reply the server's examples show: %s", async (_, it) => {
    const saved = await client(replying(it)).saveRecipe(NORMA);

    expect(saved.ok).toBe(it.response.status < 300);
  });
});
