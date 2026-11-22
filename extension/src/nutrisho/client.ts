import type { SavedRecipe } from "@/core/drafts";
import type { NutrishoClient, NutrishoError } from "@/core/ports/types";
import { savePath, toDocument, type RecipeDraft } from "@/core/recipe-draft";
import { err, ok, type Result } from "@/core/result";
import type { Settings } from "@/core/settings";
import { parseVocabulary, type Vocabulary } from "@/core/vocabulary";

/**
 * The user's Nutrisho, over `fetch` (plan 012, D10).
 *
 * An adapter: its outside edge is `fetch`, and what it needs from the browser
 * (the settings, the permission check) is injected, so ESLint's ports rule
 * holds here too. It is called from the extension's own pages, never a
 * content script, and signs in with the API key alone: never the session, so
 * the browser's cookies are not sent.
 */
export type FetchLike = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

export interface NutrishoClientDeps {
  readonly fetch: FetchLike;
  /** Read on every call, so a change on the options page takes effect at once. */
  readonly loadSettings: () => Promise<Settings>;
  readonly hasHostPermission: (serverUrl: string) => Promise<boolean>;
  readonly timeoutMs?: number;
}

export const VOCABULARY_PATH = "/recipes/api/vocabulary/";
export const SAVE_PATH = "/recipes/api/recipes/";

/** The statuses with which the server reads a save and refuses it, saying why. */
const REFUSALS = new Set([400, 409, 413]);

/** Long enough for a dev server's first request, short enough to say so. */
export const DEFAULT_TIMEOUT_MS = 10_000;

function failure(
  kind: NutrishoError["kind"],
  message: string,
  status?: number,
): Result<never, NutrishoError> {
  return err({ kind, message, ...(status === undefined ? {} : { status }) });
}

/** The server's own `{"error": ...}`, or the status line when it sent none. */
async function reasonFrom(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: unknown };
    if (typeof body.error === "string") return body.error;
  } catch {
    // Not JSON: a dev server's HTML error page, say.
  }
  return `the server answered ${response.status} ${response.statusText}`.trim();
}

/** A success, with the address it came from, which a save's link is built on. */
interface Answer {
  readonly status: number;
  readonly body: unknown;
  readonly serverUrl: string;
}

/**
 * A save's reply: `{"recipes": [{"id", "name", "renamed", "in_trash", ...}],
 * "warnings": [...]}`. The link is built on the saved address rather than the
 * reply's `url`, which names whatever host the server thinks it is, and opens
 * the recipe in edit mode. 201 made the recipe; 200 means the server already
 * had one under that id, and wrote nothing.
 */
function parseSave(answer: Answer): Result<SavedRecipe, NutrishoError> {
  const body = answer.body as {
    recipes?: {
      id?: unknown;
      name?: unknown;
      renamed?: unknown;
      in_trash?: unknown;
    }[];
    warnings?: unknown;
  } | null;
  const recipe = Array.isArray(body?.recipes) ? body.recipes[0] : undefined;
  const warnings = body?.warnings;
  if (
    typeof recipe?.id !== "string" ||
    typeof recipe.name !== "string" ||
    !Array.isArray(warnings) ||
    !warnings.every((warning) => typeof warning === "string")
  ) {
    return failure(
      "malformed-response",
      "the server's answer to the save is not in the shape this clipper reads",
      answer.status,
    );
  }
  return ok({
    openUrl: `${answer.serverUrl}/recipes/${encodeURIComponent(recipe.id)}/?edit=1`,
    name: recipe.name,
    created: answer.status === 201,
    renamed: recipe.renamed === true,
    inTrash: recipe.in_trash === true,
    warnings,
  });
}

export function createNutrishoClient(deps: NutrishoClientDeps): NutrishoClient {
  const timeoutMs = deps.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function call(
    path: string,
    body?: unknown,
  ): Promise<Result<Answer, NutrishoError>> {
    const settings = await deps.loadSettings();
    if (settings.apiKey === "") {
      return failure("no-key", "no API key is saved in the settings");
    }
    if (!(await deps.hasHostPermission(settings.serverUrl))) {
      return failure(
        "permission-missing",
        `the clipper has not been allowed to reach ${settings.serverUrl}`,
      );
    }

    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), timeoutMs);
    let response: Response;
    try {
      response = await deps.fetch(`${settings.serverUrl}${path}`, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${settings.apiKey}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        credentials: "omit",
        signal: abort.signal,
      });
    } catch (cause) {
      return abort.signal.aborted
        ? failure("timeout", `no answer within ${timeoutMs / 1000}s`)
        : failure(
            "unreachable",
            cause instanceof Error ? cause.message : String(cause),
          );
    } finally {
      clearTimeout(timer);
    }

    if (response.status === 401) {
      return failure("unauthorised", await reasonFrom(response), 401);
    }
    if (REFUSALS.has(response.status) && body !== undefined) {
      return failure("refused", await reasonFrom(response), response.status);
    }
    if (!response.ok) {
      return failure(
        "server-error",
        await reasonFrom(response),
        response.status,
      );
    }
    try {
      const answer = (await response.json()) as unknown;
      return ok({
        status: response.status,
        body: answer,
        serverUrl: settings.serverUrl,
      });
    } catch {
      return failure(
        "malformed-response",
        "the server's answer is not JSON",
        response.status,
      );
    }
  }

  return {
    async vocabulary(): Promise<Result<Vocabulary, NutrishoError>> {
      const answer = await call(VOCABULARY_PATH);
      return answer.ok ? parseVocabulary(answer.value.body) : answer;
    },

    async saveRecipe(
      draft: RecipeDraft,
    ): Promise<Result<SavedRecipe, NutrishoError>> {
      const answer = await call(savePath(draft), toDocument(draft));
      return answer.ok ? parseSave(answer.value) : answer;
    },
  };
}
