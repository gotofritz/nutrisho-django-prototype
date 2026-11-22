import { describe, expect, it } from "vitest";

import type { NutrishoErrorKind } from "@/core/ports/types";

import { listsProblem, saveProblem } from "./error-copy";

const KINDS: NutrishoErrorKind[] = [
  "no-key",
  "permission-missing",
  "unreachable",
  "timeout",
  "unauthorised",
  "refused",
  "server-error",
  "malformed-response",
];

describe("listsProblem", () => {
  // Each kind has a different fix, so each says something different.
  it("says something different for every kind of failure", () => {
    const causes = KINDS.map(
      (kind) => listsProblem({ kind, message: "x" }).cause,
    );

    expect(new Set(causes).size).toBe(KINDS.length);
  });

  it.each<[NutrishoErrorKind, "settings" | "retry"]>([
    ["no-key", "settings"],
    ["permission-missing", "settings"],
    ["unauthorised", "settings"],
    ["unreachable", "retry"],
    ["timeout", "retry"],
    ["refused", "retry"],
    ["server-error", "retry"],
    ["malformed-response", "retry"],
  ])("sends %s to the %s", (kind, fix) => {
    expect(listsProblem({ kind, message: "x" }).fix).toBe(fix);
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

  // Plan 012, M7: until M11, a refusal is shown as the server worded it.
  it("shows the server's refusal as it came", () => {
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
