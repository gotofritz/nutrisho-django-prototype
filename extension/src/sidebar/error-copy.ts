import type { ModelError, NutrishoError } from "@/core/ports/types";

/**
 * What the sidebar says when the lists will not load or a save fails (plan
 * 012, M11), in the user's words rather than the client's: a line of its own
 * for each cause, since each has a different fix.
 */
export interface Problem {
  /** What went wrong. */
  readonly cause: string;
  /** What to do about it. */
  readonly action: string;
  /**
   * Where the fix is: the options page, trying again, or a model's set-up
   * under Advanced Mode (#183).
   */
  readonly fix: "settings" | "retry" | "advanced";
}

/** The lists would not load. */
export function listsProblem(error: NutrishoError): Problem {
  return problem(error, "send the lists");
}

/** The recipe was not saved. */
export function saveProblem(error: NutrishoError): Problem {
  return problem(error, "save the recipe");
}

function problem(error: NutrishoError, task: string): Problem {
  switch (error.kind) {
    case "no-key":
      return {
        cause: "No API key is saved yet.",
        action:
          "Make one on the API keys page, under Config in your Nutrisho, then paste it into the settings.",
        fix: "settings",
      };
    case "permission-missing":
      return {
        cause: "The clipper has not been allowed to reach your Nutrisho.",
        action: "Save the settings again, and allow it when the browser asks.",
        fix: "settings",
      };
    case "not-nutrisho":
      return {
        cause: `What answered at your Nutrisho's address is not a Nutrisho, or not one this clipper can talk to (${error.message}).`,
        action:
          "Check the address in the settings, and update the server if it is older than the clipper.",
        fix: "settings",
      };
    case "key-expired":
      return {
        cause: "Your API key has expired.",
        action:
          "Make a new one on the API keys page, under Config in your Nutrisho, then paste it into the settings.",
        fix: "settings",
      };
    case "unauthorised":
      return {
        cause: `Your Nutrisho refused the API key: ${error.message}`,
        action: "Check the key in the settings, or make a new one.",
        fix: "settings",
      };
    case "unreachable":
      return {
        cause: "Nothing answered at your Nutrisho's address.",
        action:
          "Check that the server is running (make dev), and that the address in the settings is right.",
        fix: "retry",
      };
    case "timeout":
      return {
        cause: "Your Nutrisho took too long to answer.",
        action: "Try again in a moment.",
        fix: "retry",
      };
    case "refused":
      return {
        cause: `Your Nutrisho did not ${task}: ${error.message}`,
        action: "Change what it names, then try again.",
        fix: "retry",
      };
    case "too-large":
      return {
        cause: `Your Nutrisho would not ${task}, as it is too large: ${error.message}`,
        action:
          "Make it smaller, or use names from your lists where you can, then try again.",
        fix: "retry",
      };
    case "rate-limited":
      return {
        cause: "Your Nutrisho has had too many requests from this clipper.",
        action: `Wait ${waitFor(error.retryAfter)}, then try again.`,
        fix: "retry",
      };
    case "server-error":
      return {
        cause: `Your Nutrisho could not ${task}: ${error.message}`,
        action: "Try again, and look at the server's log if it happens again.",
        fix: "retry",
      };
    case "malformed-response":
      return {
        cause:
          "Your Nutrisho answered with something this clipper cannot read.",
        action:
          "The clipper and the server may be different versions: update both.",
        fix: "retry",
      };
  }
}

function waitFor(seconds: number | undefined): string {
  if (seconds === undefined) return "a minute";
  return seconds === 1 ? "a second" : `${seconds} seconds`;
}

/** The user's own model gave no rows to use (M13). */
export function modelProblem(error: ModelError): Problem {
  const said = `(it said: ${error.message})`;
  switch (error.kind) {
    case "not-set-up":
      return {
        cause: "No model is set up for ingredient lines.",
        action: "Set one up under Your models, in Advanced Mode.",
        fix: "advanced",
      };
    case "permission-missing":
      return {
        cause: "The clipper has not been allowed to reach your model.",
        action:
          "Edit it under Your models, in Advanced Mode, save it again and allow it when the browser asks.",
        fix: "advanced",
      };
    case "unreachable":
      return {
        cause: "Nothing answered at your model's address.",
        action: "Start its server, or check the address, then try again.",
        fix: "retry",
      };
    case "timeout":
      return {
        cause: "Your model did not answer in time.",
        action: "Try again; a smaller model answers sooner.",
        fix: "retry",
      };
    case "unauthorised":
      return {
        cause: `Your model refused its key ${said}.`,
        action:
          "Check its key under Your models, in Advanced Mode, or make a new one.",
        fix: "advanced",
      };
    case "unknown-model":
      return {
        cause: `Your model's server does not have that model ${said}.`,
        action: "Check the model's name under Your models, in Advanced Mode.",
        fix: "advanced",
      };
    case "rate-limited":
      return {
        cause: `Your model is asked too often, or its spending limit is spent ${said}.`,
        action: "Wait a little, or raise the limit, then try again.",
        fix: "retry",
      };
    case "server-error":
      return {
        cause: `Your model's server failed ${said}.`,
        action: "Try again; if it keeps failing, look at the server's own log.",
        fix: "retry",
      };
    case "malformed-response":
      return {
        cause: `Your model answered in a shape the clipper cannot read ${said}.`,
        action: "Try again, or a model that keeps to JSON.",
        fix: "retry",
      };
  }
}
