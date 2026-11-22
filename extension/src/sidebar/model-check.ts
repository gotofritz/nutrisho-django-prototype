import type { Problem } from "./error-copy";

/**
 * How the last check of the user's own model went (#182), for Advanced
 * Mode to say: whether it answers, before it is asked anything.
 */
export type ModelCheck =
  | { readonly kind: "checking" }
  | { readonly kind: "answering"; readonly address: string }
  | {
      readonly kind: "problem";
      readonly address: string;
      readonly problem: Problem;
    };
