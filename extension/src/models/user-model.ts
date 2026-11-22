import type { ModelSettings } from "@/core/model-settings";
import type { LineModel } from "@/core/ports/types";
import type { FetchLike } from "@/nutrisho/client";

import { createAnthropicModel } from "./anthropic";
import { createOpenAiCompatibleModel } from "./openai-compatible";
import { failure } from "./model-request";

/**
 * The user's own model, whichever backend the options page saved (plan 012,
 * M13): read on every call, so a change there takes effect at once.
 */
export interface UserModelDeps {
  readonly fetch: FetchLike;
  readonly loadSettings: () => Promise<ModelSettings>;
  readonly hasHostPermission: (address: string) => Promise<boolean>;
}

export function createUserModel(deps: UserModelDeps): LineModel {
  const local = createOpenAiCompatibleModel(deps);
  const anthropic = createAnthropicModel(deps);
  /** The adapter for the saved backend; undefined for the built-in scan. */
  async function chosen(): Promise<LineModel | undefined> {
    const { backend } = await deps.loadSettings();
    if (backend === "mlx" || backend === "llama") return local;
    if (backend === "anthropic") return anthropic;
    return undefined;
  }

  const notSetUp = failure("not-set-up", "no model is set up");

  return {
    async splitLines(lines) {
      return (await chosen())?.splitLines(lines) ?? notSetUp;
    },
    async rewriteSteps(steps) {
      return (await chosen())?.rewriteSteps(steps) ?? notSetUp;
    },
    async check() {
      return (await chosen())?.check() ?? notSetUp;
    },
  };
}
