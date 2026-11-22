import type { ModelError } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";
import type { FetchLike } from "@/nutrisho/client";

/**
 * What the model adapters share (plan 012, M13): one POST with a timeout,
 * the failures that come before any reply, and reading JSON out of a
 * model's text.
 */
export function failure(
  kind: ModelError["kind"],
  message: string,
  status?: number,
): Result<never, ModelError> {
  return err({ kind, message, ...(status === undefined ? {} : { status }) });
}

export async function jsonOf(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

/** An error's own words, in the shapes the servers use. */
export function messageOf(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const { error, message } = body as { error?: unknown; message?: unknown };
  if (typeof error === "string") return error;
  if (typeof error === "object" && error !== null) {
    const nested = (error as { message?: unknown }).message;
    if (typeof nested === "string") return nested;
  }
  return typeof message === "string" ? message : undefined;
}

/**
 * The JSON in a model's text: past a `<think>` block, out of a code fence,
 * or between the first `{` and the last `}`.
 */
export function jsonIn(content: string): Result<unknown, ModelError> {
  const text = content.replace(/<think>[\s\S]*?<\/think>/g, "");
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start !== -1 && end > start) {
    try {
      return ok(JSON.parse(text.slice(start, end + 1)) as unknown);
    } catch {
      // Not JSON after all: said below.
    }
  }
  return failure("malformed-response", "the model's answer is not JSON");
}

/** A request, giving up after `timeoutMs`; the reply, or why there is none. */
async function send(
  fetch: FetchLike,
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string },
  timeoutMs: number,
): Promise<Result<Response, ModelError>> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeoutMs);
  try {
    return ok(
      await fetch(url, {
        ...init,
        headers: { Accept: "application/json", ...init.headers },
        credentials: "omit",
        signal: abort.signal,
      }),
    );
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
}

/** POST JSON, giving up after `timeoutMs`; the reply, or why there is none. */
export function post(
  fetch: FetchLike,
  url: string,
  headers: Record<string, string>,
  body: unknown,
  timeoutMs: number,
): Promise<Result<Response, ModelError>> {
  return send(
    fetch,
    url,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    },
    timeoutMs,
  );
}

/** GET with no body: a check that sends nothing of the recipe. */
export function get(
  fetch: FetchLike,
  url: string,
  headers: Record<string, string>,
  timeoutMs: number,
): Promise<Result<Response, ModelError>> {
  return send(fetch, url, { method: "GET", headers }, timeoutMs);
}

/** A check is quick, or the model is not there. */
export const CHECK_TIMEOUT_MS = 10_000;
