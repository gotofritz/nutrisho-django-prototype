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
const REFUSALS = new Set([400, 409]);

/** An endpoint that is not there, or not for this method: not a Nutrisho, or too old. */
const NOT_HERE = new Set([404, 405]);

/** Long enough for a dev server's first request, short enough to say so. */
export const DEFAULT_TIMEOUT_MS = 10_000;

function failure(
  kind: NutrishoError["kind"],
  message: string,
  status?: number,
): Result<never, NutrishoError> {
  return err({ kind, message, ...(status === undefined ? {} : { status }) });
}

/** The body as JSON, or undefined when it is not. */
async function jsonOf(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

/** The server's refusal, `{"error": "...", "code": "..."}`, or undefined for any other shape. */
function refusalOf(
  body: unknown,
): { readonly error: string; readonly code: string } | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const { error, code } = body as { error?: unknown; code?: unknown };
  if (typeof error !== "string") return undefined;
  if (code !== undefined && typeof code !== "string") return undefined;
  return { error, code: code ?? "" };
}

function statusLine(response: Response): string {
  return `the server answered ${response.status} ${response.statusText}`.trim();
}

/** `Retry-After` in seconds; its other form, a date, the server never sends. */
function retryAfterOf(response: Response): number | undefined {
  const header = response.headers.get("Retry-After")?.trim() ?? "";
  return /^\d+$/.test(header) ? Number(header) : undefined;
}

/** A reply that is not a success, by the cause the user has to fix. */
async function failed(
  response: Response,
  isSave: boolean,
): Promise<Result<never, NutrishoError>> {
  const { status } = response;
  const refusal = refusalOf(await jsonOf(response));
  if (status >= 500) {
    return failure(
      "server-error",
      refusal?.error ?? statusLine(response),
      status,
    );
  }
  if (NOT_HERE.has(status) || refusal === undefined) {
    return failure("not-nutrisho", statusLine(response), status);
  }
  if (status === 401) {
    const kind =
      refusal.code === "token_expired" ? "key-expired" : "unauthorised";
    return failure(kind, refusal.error, status);
  }
  if (status === 429) {
    const retryAfter = retryAfterOf(response);
    return err({
      kind: "rate-limited",
      message: refusal.error,
      status,
      ...(retryAfter === undefined ? {} : { retryAfter }),
    });
  }
  if (status === 413) return failure("too-large", refusal.error, status);
  if (isSave && REFUSALS.has(status)) {
    return failure("refused", refusal.error, status);
  }
  return failure("server-error", refusal.error, status);
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

    if (!response.ok) return failed(response, body !== undefined);
    const answer = await jsonOf(response);
    if (answer === undefined) {
      return failure(
        "not-nutrisho",
        "the server's answer is not JSON, which a Nutrisho's always is",
        response.status,
      );
    }
    return ok({
      status: response.status,
      body: answer,
      serverUrl: settings.serverUrl,
    });
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
