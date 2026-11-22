import { describe, expect, it } from "vitest";

import type { NutrishoErrorKind } from "@/core/ports/types";

import { listsProblem, modelProblem, saveProblem } from "./error-copy";

/** Every kind, and where its fix is: a record, so a new kind must be added. */
const FIXES: Record<NutrishoErrorKind, "settings" | "retry"> = {
  "no-key": "settings",
  "permission-missing": "settings",
  "not-nutrisho": "settings",
  unauthorised: "settings",
  "key-expired": "settings",
  unreachable: "retry",
  timeout: "retry",
  refused: "retry",
  "too-large": "retry",
  "rate-limited": "retry",
  "server-error": "retry",
  "malformed-response": "retry",
};
const KINDS = Object.keys(FIXES) as NutrishoErrorKind[];

describe("listsProblem", () => {
  // Each kind has a different fix, so each says something different.
  it("says something different for every kind of failure", () => {
    const causes = KINDS.map(
      (kind) => listsProblem({ kind, message: "x" }).cause,
    );

    expect(new Set(causes).size).toBe(KINDS.length);
  });

  it.each(Object.entries(FIXES) as [NutrishoErrorKind, string][])(
    "sends %s to the %s",
    (kind, fix) => {
      expect(listsProblem({ kind, message: "x" }).fix).toBe(fix);
    },
  );

  // Plan 012, M11: an expired key needs a new one, not a check.
  it("tells someone whose key expired to make a new one", () => {
    const problem = listsProblem({ kind: "key-expired", message: "x" });

    expect(problem.cause).toBe("Your API key has expired.");
    expect(problem.action).toContain("API keys page");
  });

  it("says how long to wait, when the server said", () => {
    expect(
      listsProblem({ kind: "rate-limited", message: "x", retryAfter: 42 })
        .action,
    ).toBe("Wait 42 seconds, then try again.");
    expect(
      listsProblem({ kind: "rate-limited", message: "x", retryAfter: 1 })
        .action,
    ).toBe("Wait a second, then try again.");
    expect(listsProblem({ kind: "rate-limited", message: "x" }).action).toBe(
      "Wait a minute, then try again.",
    );
  });

  it("says when what answered is not a Nutrisho", () => {
    const problem = listsProblem({
      kind: "not-nutrisho",
      status: 404,
      message: "the server answered 404 Not Found",
    });

    expect(problem.cause).toContain("is not a Nutrisho");
    expect(problem.action).toContain("address");
  });

  it("tells someone with no key how to make one", () => {
    expect(listsProblem({ kind: "no-key", message: "" }).action).toContain(
      "API keys page",
    );
  });

  it("passes on the server's own reason for a refusal", () => {
    expect(
      listsProblem({
        kind: "server-error",
        status: 500,
        message: "the server answered 500",
      }).cause,
    ).toContain("500");
  });
});

describe("saveProblem", () => {
  it("says something different for every kind of failure", () => {
    const causes = KINDS.map(
      (kind) => saveProblem({ kind, message: "x" }).cause,
    );

    expect(new Set(causes).size).toBe(KINDS.length);
  });

  // The sidebar puts the field in the editor's words first (explainRefusal).
  it("shows the server's refusal with its reason", () => {
    const problem = saveProblem({
      kind: "refused",
      status: 400,
      message: "document.recipes[0].recipe_name is required.",
    });

    expect(problem.cause).toBe(
      "Your Nutrisho did not save the recipe: document.recipes[0].recipe_name is required.",
    );
    expect(problem.fix).toBe("retry");
  });

  it("passes on why a save was too large", () => {
    expect(
      saveProblem({
        kind: "too-large",
        status: 413,
        message:
          "One request may make at most 150 new names; this one would make 151.",
      }).cause,
    ).toBe(
      "Your Nutrisho would not save the recipe, as it is too large: One request may make at most 150 new names; this one would make 151.",
    );
  });

  it("is about the save, not the lists", () => {
    expect(
      saveProblem({ kind: "server-error", message: "500" }).cause,
    ).toContain("save");
  });

  it("sends the same kinds to the settings as the lists do", () => {
    for (const kind of KINDS) {
      expect(saveProblem({ kind, message: "x" }).fix).toBe(
        listsProblem({ kind, message: "x" }).fix,
      );
    }
  });
});

// Plan 012, M13 (#181): the user's own model, a sentence and a fix each.
describe("modelProblem", () => {
  it.each([
    ["not-set-up", "No model is set up for ingredient lines.", "settings"],
    [
      "permission-missing",
      "The clipper has not been allowed to reach your model.",
      "settings",
    ],
    ["unreachable", "Nothing answered at your model's address.", "retry"],
    ["timeout", "Your model did not answer in time.", "retry"],
    ["unauthorised", "Your model refused its key (it said: x).", "settings"],
    [
      "unknown-model",
      "Your model's server does not have that model (it said: x).",
      "settings",
    ],
    [
      "rate-limited",
      "Your model is asked too often, or its spending limit is spent (it said: x).",
      "retry",
    ],
    ["server-error", "Your model's server failed (it said: x).", "retry"],
    [
      "malformed-response",
      "Your model answered in a shape the clipper cannot read (it said: x).",
      "retry",
    ],
  ] as const)("explains %s", (kind, cause, fix) => {
    const problem = modelProblem({ kind, message: "x" });

    expect(problem.cause).toBe(cause);
    expect(problem.fix).toBe(fix);
    expect(problem.action).not.toBe("");
  });
});
