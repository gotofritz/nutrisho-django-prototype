import type { SavedRecipe } from "../../drafts";
import type { RecipeDraft } from "../../recipe-draft";
import { ok, type Result } from "../../result";
import { EMPTY_VOCABULARY, type Vocabulary } from "../../vocabulary";
import type { NutrishoClient, NutrishoError } from "../types";

export interface FakeNutrishoClient extends NutrishoClient {
  /** What every later `vocabulary()` answers with. */
  answerVocabulary(answer: Result<Vocabulary, NutrishoError>): void;
  /** What every later `saveRecipe()` answers with, instead of a new recipe. */
  answerSave(answer: Result<SavedRecipe, NutrishoError>): void;
  /** How many times `vocabulary()` was called. */
  readonly calls: number;
  /** Every draft `saveRecipe()` was sent, in order. */
  readonly sent: readonly RecipeDraft[];
}

/** An in-memory `NutrishoClient`, answering with whatever a test sets. */
export function createFakeNutrishoClient(): FakeNutrishoClient {
  let answer: Result<Vocabulary, NutrishoError> = ok(EMPTY_VOCABULARY);
  let saveAnswer: Result<SavedRecipe, NutrishoError> | undefined;
  let calls = 0;
  const sent: RecipeDraft[] = [];

  return {
    answerVocabulary(next: Result<Vocabulary, NutrishoError>): void {
      answer = next;
    },

    answerSave(next: Result<SavedRecipe, NutrishoError>): void {
      saveAnswer = next;
    },

    get calls() {
      return calls;
    },

    get sent() {
      return sent;
    },

    async vocabulary(): Promise<Result<Vocabulary, NutrishoError>> {
      calls += 1;
      return answer;
    },

    async saveRecipe(
      draft: RecipeDraft,
    ): Promise<Result<SavedRecipe, NutrishoError>> {
      sent.push(draft);
      return (
        saveAnswer ??
        ok({
          openUrl: `http://localhost:8987/recipes/${draft.id}/?edit=1`,
          name: draft.name,
          created: true,
          renamed: false,
          inTrash: false,
          warnings: [],
        })
      );
    },
  };
}
