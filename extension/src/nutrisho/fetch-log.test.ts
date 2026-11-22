import { describe, expect, it, vi } from "vitest";

import type { FetchLike } from "./client";
import { loggedFetch, type LogEntry } from "./fetch-log";

const URL = "http://127.0.0.1:8987/recipes/api/vocabulary/";

/** A clock that moves on 42 ms each time it is read. */
function ticking() {
  let ms = Date.UTC(2026, 10, 22, 4, 26, 0);
  return () => new Date((ms += 42));
}

function logging(fetch: FetchLike) {
  const entries: LogEntry[] = [];
  const logged = loggedFetch(fetch, (entry) => entries.push(entry), ticking());
  return { logged, lines: () => entries.map((entry) => entry.text), entries };
}

// Plan 012, M12 (#179): Advanced Mode's log is what went to the server and
// what came back, and nothing else.
describe("loggedFetch", () => {
  it("logs the request and the reply, with its size and how long it took", async () => {
    const { logged, lines, entries } = logging(
      async () =>
        new Response('{"user":"cook"}', { status: 200, statusText: "OK" }),
    );

    const response = await logged(URL, { method: "GET" });

    expect(await response.json()).toEqual({ user: "cook" });
    expect(lines()).toEqual([`→ GET ${URL}`, "← 200 OK · 15 B · 42 ms"]);
    expect(entries[0]?.at).toEqual(
      new Date(Date.UTC(2026, 10, 22, 4, 26, 0, 42)),
    );
  });

  it("logs the size of what it sends, and kilobytes once there are many", async () => {
    const { logged, lines } = logging(
      async () =>
        new Response("x".repeat(2_345), { status: 201, statusText: "Created" }),
    );

    await logged(URL, { method: "POST", body: "y".repeat(1_200) });

    expect(lines()).toEqual([
      `→ POST ${URL} · 1.2 kB`,
      "← 201 Created · 2.3 kB · 42 ms",
    ]);
  });

  it("takes GET when no method is named", async () => {
    const { logged, lines } = logging(async () => new Response(""));

    await logged(URL);

    expect(lines()[0]).toBe(`→ GET ${URL}`);
  });

  it("logs a refusal as it came", async () => {
    const { logged, lines } = logging(
      async () =>
        new Response('{"error":"no"}', {
          status: 401,
          statusText: "Unauthorized",
        }),
    );

    const response = await logged(URL);

    expect(response.status).toBe(401);
    expect(lines()[1]).toBe("← 401 Unauthorized · 14 B · 42 ms");
  });

  it("logs a request that got no reply, and still fails it", async () => {
    const { logged, lines } = logging(async () => {
      throw new TypeError("NetworkError when attempting to fetch resource.");
    });

    await expect(logged(URL)).rejects.toThrow(TypeError);

    expect(lines()[1]).toBe(
      "✕ TypeError: NetworkError when attempting to fetch resource. · 42 ms",
    );
  });

  // D11: the key is never shown again, here neither.
  it("never logs the headers, so never the key", async () => {
    const { logged, lines } = logging(async () => new Response(""));

    await logged(URL, {
      headers: { Authorization: "Bearer nsh_secret-key" },
    });

    expect(lines().join("\n")).not.toContain("nsh_secret");
  });

  it("hands the reply on unread", async () => {
    const fetch = vi.fn<FetchLike>(async () => new Response("body"));
    const { logged } = logging(fetch);

    const response = await logged(URL, { method: "GET" });

    expect(response.bodyUsed).toBe(false);
    expect(await response.text()).toBe("body");
    expect(fetch).toHaveBeenCalledWith(URL, { method: "GET" });
  });
});
