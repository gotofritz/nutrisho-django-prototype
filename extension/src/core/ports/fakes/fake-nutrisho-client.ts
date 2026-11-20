import { ok, type Result } from "../../result";
import { EMPTY_VOCABULARY, type Vocabulary } from "../../vocabulary";
import type { NutrishoClient, NutrishoError } from "../types";

export interface FakeNutrishoClient extends NutrishoClient {
  /** What every later `vocabulary()` answers with. */
  answerVocabulary(answer: Result<Vocabulary, NutrishoError>): void;
  /** How many times `vocabulary()` was called. */
  readonly calls: number;
}

/** An in-memory `NutrishoClient`, answering with whatever a test sets. */
export function createFakeNutrishoClient(): FakeNutrishoClient {
  let answer: Result<Vocabulary, NutrishoError> = ok(EMPTY_VOCABULARY);
  let calls = 0;

  return {
    answerVocabulary(next: Result<Vocabulary, NutrishoError>): void {
      answer = next;
    },

    get calls() {
      return calls;
    },

    async vocabulary(): Promise<Result<Vocabulary, NutrishoError>> {
      calls += 1;
      return answer;
    },
  };
}
