import { describe, expect, it } from "vitest";

import { jsonIn, messageOf } from "./model-request";

describe("jsonIn", () => {
  it.each([
    ['{"rows": []}', { rows: [] }],
    ['<think>\nhmm\n</think>\n{"rows": []}', { rows: [] }],
    ['```json\n{"rows": []}\n```', { rows: [] }],
    ['Sure! {"rows": []} Hope that helps.', { rows: [] }],
  ])("finds the JSON in %j", (content, json) => {
    expect(jsonIn(content)).toEqual({ ok: true, value: json });
  });

  it("says when there is none", () => {
    expect(jsonIn("Here are your rows:")).toEqual({
      ok: false,
      error: {
        kind: "malformed-response",
        message: "the model's answer is not JSON",
      },
    });
  });
});

describe("messageOf", () => {
  it.each([
    [{ error: { message: "nested" } }, "nested"],
    [{ error: "flat" }, "flat"],
    [{ message: "top" }, "top"],
    ["text", undefined],
    [null, undefined],
  ])("reads an error's words from %j", (body, message) => {
    expect(messageOf(body)).toBe(message);
  });
});
