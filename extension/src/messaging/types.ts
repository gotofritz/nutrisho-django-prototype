import type { PageCapture } from "@/core/capture";
import type { Result } from "@/core/result";
import type { ExtensionContext, TransportErrorKind } from "@/platform/types";

/**
 * Every message the extension sends, as one discriminated union on `type`
 *. Background, content script, and sidebar all import this module, and
 * that shared import is the only thing keeping the three from drifting apart.
 *
 * Adding a message means adding a member here and its reply in `ResponseMap`;
 * the compiler then finds every place that has to change.
 */
export type Message =
  | { readonly type: "ping" }
  /** Background to a content script: read the page's current selection. */
  | { readonly type: "capture-selection" };

export type MessageType = Message["type"];

export type MessageOf<K extends MessageType> = Extract<Message, { type: K }>;

/** What each message is answered with, keyed by the message's `type`. */
export interface ResponseMap {
  /** Which context answered — the sidebar uses it to know the background is up. */
  readonly ping: { readonly from: ExtensionContext };
  /**
   * What the page gave up. Blind spots arrive as warnings on the capture
   * rather than as a failed reply: a degraded capture is still a clipping,
   * and the warning is what makes the degradation visible.
   */
  readonly "capture-selection": PageCapture;
}

export type ResponseOf<K extends MessageType> = ResponseMap[K];

/**
 * Why a message did not produce its reply. The transport's own failures pass
 * through unchanged; the rest happen at the far end.
 */
export type MessagingErrorKind =
  | TransportErrorKind
  /** No handler is registered for this type, or it was not a message at all. */
  | "unknown-message"
  /** A handler threw. The exception does not escape the far context. */
  | "handler-failed"
  /** Something answered, but not with the `Result` every handler owes. */
  | "malformed-reply";

export interface MessagingError {
  readonly kind: MessagingErrorKind;
  readonly message: string;
}

/** Every message is answered with a Result, never a bare value. */
export type Reply<K extends MessageType> = Result<
  ResponseOf<K>,
  MessagingError
>;
