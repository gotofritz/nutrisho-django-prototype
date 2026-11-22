/**
 * The reply shape every port and every message handler returns.
 *
 * A union rather than a thrown error: `AGENTS.md` requires extension
 * messaging and server failures to be handled explicitly, and a caller
 * that forgets the failure branch of a union is a type error rather than an
 * unhandled rejection in production.
 */
export interface Ok<T> {
  readonly ok: true;
  readonly value: T;
}

export interface Err<E> {
  readonly ok: false;
  readonly error: E;
}

export type Result<T, E> = Ok<T> | Err<E>;

export function ok<T>(value: T): Ok<T> {
  return { ok: true, value };
}

export function err<E>(error: E): Err<E> {
  return { ok: false, error };
}

export function isOk<T, E>(result: Result<T, E>): result is Ok<T> {
  return result.ok;
}

export function isErr<T, E>(result: Result<T, E>): result is Err<E> {
  return !result.ok;
}

/**
 * Whether an untrusted value is Result-shaped.
 *
 * Anything on the page, and any other extension, can send this extension a
 * message, so a reply arriving over the message channel is `unknown` until
 * proven otherwise.
 */
export function isResult(value: unknown): value is Result<unknown, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    "ok" in value &&
    typeof (value as { ok: unknown }).ok === "boolean"
  );
}
