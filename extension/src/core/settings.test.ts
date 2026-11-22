import { describe, expect, it } from "vitest";

import {
  DEFAULT_SETTINGS,
  checkSettings,
  hostPatternFor,
  keysPageFor,
  readSettings,
} from "./settings";

const KEY = "nsh_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";

describe("the defaults", () => {
  // Plan 012, D17: built against `make dev`, on loopback.
  it("point at the dev server and hold no key", () => {
    expect(DEFAULT_SETTINGS).toEqual({
      serverUrl: "http://localhost:8987",
      apiKey: "",
    });
  });
});

describe("checkSettings", () => {
  it("accepts a loopback address and a key", () => {
    expect(
      checkSettings({ serverUrl: "http://localhost:8987", apiKey: KEY }),
    ).toEqual({
      ok: true,
      value: { serverUrl: "http://localhost:8987", apiKey: KEY },
    });
  });

  it("keeps only the address's origin, and trims what was typed", () => {
    expect(
      checkSettings({
        serverUrl: "  http://127.0.0.1:8000/recipes/  ",
        apiKey: ` ${KEY}\n`,
      }),
    ).toEqual({
      ok: true,
      value: { serverUrl: "http://127.0.0.1:8000", apiKey: KEY },
    });
  });

  it.each([
    ["", "missing"],
    ["localhost:8987", "not-a-url"],
    ["ftp://localhost", "not-http"],
    ["https://localhost:8987", "not-http"],
    ["http://recipes.example.com", "not-loopback"],
    ["http://[::1]:8987", "not-loopback"],
  ])("refuses the address %j (%s)", (serverUrl, code) => {
    const checked = checkSettings({ serverUrl, apiKey: KEY });

    expect(checked.ok).toBe(false);
    expect(!checked.ok && checked.error.map((issue) => issue.code)).toEqual([
      code,
    ]);
    expect(!checked.ok && checked.error[0]?.field).toBe("serverUrl");
  });

  it.each([
    ["", "missing"],
    ["abcdef", "not-a-key"],
    ["nsh_", "not-a-key"],
    ["nsh_has spaces in it", "not-a-key"],
  ])("refuses the key %j (%s)", (apiKey, code) => {
    const checked = checkSettings({
      serverUrl: "http://localhost:8987",
      apiKey,
    });

    expect(!checked.ok && checked.error).toEqual([
      expect.objectContaining({ field: "apiKey", code }),
    ]);
  });

  it("names every problem at once", () => {
    const checked = checkSettings({ serverUrl: "", apiKey: "" });

    expect(!checked.ok && checked.error.map((issue) => issue.field)).toEqual([
      "serverUrl",
      "apiKey",
    ]);
  });
});

describe("readSettings", () => {
  it("reads back what was saved", () => {
    expect(
      readSettings({ serverUrl: "http://127.0.0.1:8000", apiKey: KEY }),
    ).toEqual({ serverUrl: "http://127.0.0.1:8000", apiKey: KEY });
  });

  // An extension that will not start because of its own storage is the
  // failure this shape exists to make impossible.
  it.each([
    ["nothing", undefined],
    ["a string", "settings"],
    ["the wrong types", { serverUrl: 8987, apiKey: null }],
  ])("degrades %s to the defaults", (_, stored) => {
    expect(readSettings(stored)).toEqual(DEFAULT_SETTINGS);
  });

  it("degrades one bad value without losing the other", () => {
    expect(
      readSettings({ serverUrl: "http://evil.example", apiKey: KEY }),
    ).toEqual({ serverUrl: DEFAULT_SETTINGS.serverUrl, apiKey: KEY });
  });
});

describe("hostPatternFor", () => {
  // Plan 012, M6: MDN says Firefox's match patterns take no port, so the
  // permission names the host alone, and covers every port on it.
  it("names the host without its port", () => {
    expect(hostPatternFor("http://localhost:8987")).toBe("http://localhost/*");
    expect(hostPatternFor("http://127.0.0.1:8000")).toBe("http://127.0.0.1/*");
  });
});

describe("keysPageFor", () => {
  // #150: the server's page where a user makes their own key.
  it("is the API keys page on the server", () => {
    expect(keysPageFor("http://localhost:8987")).toBe(
      "http://localhost:8987/recipes/keys/",
    );
    expect(keysPageFor(" http://127.0.0.1:8000/ ")).toBe(
      "http://127.0.0.1:8000/recipes/keys/",
    );
  });

  it("is undefined for an address the settings would refuse", () => {
    expect(keysPageFor("")).toBeUndefined();
    expect(keysPageFor("localhost:8987")).toBeUndefined();
    expect(keysPageFor("https://example.com")).toBeUndefined();
  });
});
