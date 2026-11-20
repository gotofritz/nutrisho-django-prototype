import type { NutrishoClient, NutrishoError } from "@/core/ports/types";
import { err, type Result } from "@/core/result";
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

export function createNutrishoClient(deps: NutrishoClientDeps): NutrishoClient {
  const timeoutMs = deps.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function get(path: string): Promise<Result<unknown, NutrishoError>> {
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
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${settings.apiKey}`,
        },
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
    if (!response.ok) {
      return failure(
        "server-error",
        await reasonFrom(response),
        response.status,
      );
    }
    try {
      return { ok: true, value: (await response.json()) as unknown };
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
      const body = await get(VOCABULARY_PATH);
      return body.ok ? parseVocabulary(body.value) : body;
    },
  };
}
