import type { Clipping } from "../clipping";
import type { Drafts, SavedRecipe } from "../drafts";
import type { ModelChoices } from "../model-settings";
import type { RecipeDraft, Step } from "../recipe-draft";
import type { Result } from "../result";
import type { Settings } from "../settings";
import type { Vocabulary } from "../vocabulary";

/**
 * The ports the domain layer talks to (plan 012, D13). Interfaces only: the
 * real implementations are adapters, storage in `src/platform/` and the
 * server's client in `src/nutrisho/`, and every one ships an in-memory fake
 * under `fakes/`, which is what tests run against.
 *
 * Nothing here mentions HTTP, `browser.*` or Svelte. That is the point.
 */

export type StoreErrorKind =
  | "read-failed"
  | "write-failed"
  /** Something is stored under the key, but not in a shape this version reads. */
  | "malformed-stored-value";

/** Why a store could not answer. One shape for every store. */
export interface StoreError {
  readonly kind: StoreErrorKind;
  readonly message: string;
}

/**
 * What the user configured. `load` answers with whole `Settings`: a stored
 * value that does not check degrades to its default rather than failing the
 * read, so the only failure left is storage itself refusing.
 */
export interface SettingsStore {
  load(): Promise<Result<Settings, StoreError>>;
  save(settings: Settings): Promise<Result<void, StoreError>>;
}

/** Which scanner reads ingredient lines, and where its model is (M13). */
export interface ModelSettingsStore {
  load(): Promise<Result<ModelChoices, StoreError>>;
  save(choices: ModelChoices): Promise<Result<void, StoreError>>;
}

/** The last thing clipped, which the sidebar shows (M6). */
export interface ClippingStore {
  load(): Promise<Result<Clipping | undefined, StoreError>>;
  save(clipping: Clipping): Promise<Result<void, StoreError>>;
  clear(): Promise<Result<void, StoreError>>;
}

/** Every draft the sidebar holds, so one survives the sidebar closing (M7). */
export interface DraftStore {
  load(): Promise<Result<Drafts, StoreError>>;
  save(drafts: Drafts): Promise<Result<void, StoreError>>;
}

/**
 * Why the server did not answer, or answered with a refusal. Each kind has a
 * different fix, so the client tells them apart rather than collapsing them.
 */
export type NutrishoErrorKind =
  /** No API key is saved yet: the clipper is not set up. */
  | "no-key"
  /** The server's host has not been granted (Firefox grants none at install). */
  | "permission-missing"
  /** Nothing answered at the address: the server is not running, or is elsewhere. */
  | "unreachable"
  /** The server answered, but not in time. */
  | "timeout"
  /**
   * Something answered that is not a Nutrisho: a 404 or 405 on the endpoint,
   * a success that is not JSON, or a refusal not in the server's shape.
   */
  | "not-nutrisho"
  /** A 401: the key is wrong, or was deleted. */
  | "unauthorised"
  /** A 401 with `code: token_expired` (#149): the key was right, but has expired. */
  | "key-expired"
  /** A 400 or 409 to a save: the server read it and said no, and why. */
  | "refused"
  /** A 413: too many recipes, too many new names, or too large a body (#149). */
  | "too-large"
  /** A 429 (#149): wait `retryAfter` seconds, if the server said. */
  | "rate-limited"
  /** A 5xx, or any other status that is not a success. */
  | "server-error"
  /** A JSON success that is not the shape the server's example shows. */
  | "malformed-response";

export interface NutrishoError {
  readonly kind: NutrishoErrorKind;
  readonly message: string;
  /** The HTTP status, when there was one. */
  readonly status?: number;
  /** For `rate-limited`: the seconds `Retry-After` says to wait. */
  readonly retryAfter?: number;
}

/** The user's Nutrisho, over its two JSON endpoints (D10). */
export interface NutrishoClient {
  /** The lists the sidebar loads when it opens (D4). Never throws. */
  vocabulary(): Promise<Result<Vocabulary, NutrishoError>>;
  /** Save the draft under its own id; a second save answers with the first's recipe. */
  saveRecipe(draft: RecipeDraft): Promise<Result<SavedRecipe, NutrishoError>>;
}

/** Why the user's own model gave no answer to read (plan 012, M13). */
export type ModelErrorKind =
  /** No model is set up: the built-in scan is all there is. */
  | "not-set-up"
  /** The user has not allowed the clipper to reach the model's address. */
  | "permission-missing"
  /** Nothing answered at the address: the model is not running. */
  | "unreachable"
  /** It answered, but not in time. */
  | "timeout"
  /** A 401 or 403: the model's key is wrong, missing or revoked. */
  | "unauthorised"
  /** A 429: too many requests, or the account's limit is spent. */
  | "rate-limited"
  /** The model named in the settings is not there to run. */
  | "unknown-model"
  /** Any other status that is not a success. */
  | "server-error"
  /** A success that is not the provider's shape, or holds no JSON. */
  | "malformed-response";

export interface ModelError {
  readonly kind: ModelErrorKind;
  readonly message: string;
  readonly status?: number;
}

/**
 * The user's own model (D20), which splits ingredient lines into rows and
 * rewrites the method.
 */
export interface LineModel {
  /**
   * The model's answer for these lines, as JSON and unchecked:
   * `readModelAnswer` (core/model-answer) decides what of it is used.
   * Never throws.
   */
  splitLines(lines: readonly string[]): Promise<Result<unknown, ModelError>>;
  /**
   * The model's rewrite of these steps, as JSON and unchecked:
   * `readStepsAnswer` (core/model-steps) decides whether it is used.
   * Never throws.
   */
  rewriteSteps(steps: readonly Step[]): Promise<Result<unknown, ModelError>>;
  /**
   * Whether the model answers at all, sending nothing of the recipe (#182).
   * Never throws.
   */
  check(): Promise<Result<void, ModelError>>;
}
