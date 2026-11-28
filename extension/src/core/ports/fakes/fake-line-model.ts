import type { Step } from "../../recipe-draft";
import { err, ok, type Result } from "../../result";
import type { LineModel, ModelError } from "../types";

export interface FakeLineModel extends LineModel {
  /** What every later `splitLines()`, `rewriteSteps()` or `rewriteBlurb()` answers with. */
  answer(next: Result<unknown, ModelError>): void;
  /** The lines of each call, in order. */
  readonly sent: readonly (readonly string[])[];
  /** The steps of each `rewriteSteps()`, in order. */
  readonly stepsSent: readonly (readonly Step[])[];
  /** The blurb of each `rewriteBlurb()`, in order. */
  readonly blurbsSent: readonly string[];
  /** How often `check()` was called; it fails as `answer` fails. */
  readonly checks: number;
}

/** An in-memory model: answers as told, and says what it was sent. */
export function createFakeLineModel(): FakeLineModel {
  let next: Result<unknown, ModelError> = err({
    kind: "not-set-up",
    message: "no model is set up",
  });
  const sent: (readonly string[])[] = [];
  const stepsSent: (readonly Step[])[] = [];
  const blurbsSent: string[] = [];
  let checks = 0;
  return {
    answer(answer) {
      next = answer;
    },
    get sent() {
      return sent;
    },
    get stepsSent() {
      return stepsSent;
    },
    get blurbsSent() {
      return blurbsSent;
    },
    get checks() {
      return checks;
    },
    async check() {
      checks += 1;
      return next.ok ? ok(undefined) : next;
    },
    async splitLines(lines) {
      sent.push([...lines]);
      return next;
    },
    async rewriteSteps(steps) {
      stepsSent.push(steps.map((step) => ({ ...step })));
      return next;
    },
    async rewriteBlurb(blurb) {
      blurbsSent.push(blurb);
      return next;
    },
  };
}
