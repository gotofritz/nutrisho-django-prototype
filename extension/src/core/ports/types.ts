import type { Clipping } from "../clipping";
import type { Drafts, SavedRecipe } from "../drafts";
import type { RecipeDraft } from "../recipe-draft";
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
  /** No API key is saved yet. */
  | "no-key"
  /** The server's host has not been granted (Firefox grants none at install). */
  | "permission-missing"
  /** Nothing answered at the address: the server is not running, or is elsewhere. */
  | "unreachable"
  /** The server answered, but not in time. */
  | "timeout"
  /** A 401: the key is wrong, or was deleted. */
  | "unauthorised"
  /** A 400, 409 or 413: the server read the request and said no, and why. */
  | "refused"
  /** Any other status that is not a success. */
  | "server-error"
  /** A success whose body is not the shape the server's example shows. */
  | "malformed-response";

export interface NutrishoError {
  readonly kind: NutrishoErrorKind;
  readonly message: string;
  /** The HTTP status, when there was one. */
  readonly status?: number;
}

/** The user's Nutrisho, over its two JSON endpoints (D10). */
export interface NutrishoClient {
  /** The lists the sidebar loads when it opens (D4). Never throws. */
  vocabulary(): Promise<Result<Vocabulary, NutrishoError>>;
  /** Save the draft under its own id; a second save answers with the first's recipe. */
  saveRecipe(draft: RecipeDraft): Promise<Result<SavedRecipe, NutrishoError>>;
}
