import { describe, expect, it } from "vitest";

import type { NutrishoErrorKind } from "@/core/ports/types";

import { listsProblem } from "./error-copy";

const KINDS: NutrishoErrorKind[] = [
  "no-key",
  "permission-missing",
  "unreachable",
  "timeout",
  "unauthorised",
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
    ["server-error", "retry"],
    ["malformed-response", "retry"],
  ])("sends %s to the %s", (kind, fix) => {
    expect(listsProblem({ kind, message: "x" }).fix).toBe(fix);
  });

  it("tells someone with no key how to make one", () => {
    expect(listsProblem({ kind: "no-key", message: "" }).action).toContain(
      "create_api_token",
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
