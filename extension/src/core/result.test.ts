import { describe, expect, it } from "vitest";

import { err, isErr, isOk, isResult, ok } from "./result";

describe("Result", () => {
  it("wraps a value as a success", () => {
    expect(ok(42)).toEqual({ ok: true, value: 42 });
  });

  it("wraps a failure without throwing it", () => {
    expect(err({ kind: "nope" })).toEqual({
      ok: false,
      error: { kind: "nope" },
    });
  });

  it("narrows a success with isOk", () => {
    const result = ok("value");

    expect(isOk(result)).toBe(true);
    expect(isErr(result)).toBe(false);
  });

  it("narrows a failure with isErr", () => {
    const result = err("boom");

    expect(isErr(result)).toBe(true);
    expect(isOk(result)).toBe(false);
  });
});

describe("isResult", () => {
  it.each([
    ["a success", { ok: true, value: 1 }],
    ["a failure", { ok: false, error: "boom" }],
  ])("accepts %s", (_label, value) => {
    expect(isResult(value)).toBe(true);
  });

  // A reply crossing the extension message channel is `unknown` until proven
  // otherwise: anything may send this context a message.
  it.each([
    ["undefined", undefined],
    ["null", null],
    ["a bare value", "pong"],
    ["an object with no ok field", { value: 1 }],
    ["an object whose ok is not a boolean", { ok: "yes", value: 1 }],
  ])("rejects %s", (_label, value) => {
    expect(isResult(value)).toBe(false);
  });
});
