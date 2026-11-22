/**
 * Small shared types for the platform layer. Everything that touches
 * `browser.*` lives under `src/platform/`; everything above it depends on
 * these types and on the port interfaces, never on the browser directly.
 */

/** The three contexts an extension message can come from or go to. */
export type ExtensionContext = "background" | "content" | "sidebar";

/** Who sent a message, reduced to what this extension actually uses. */
export interface MessageSender {
  readonly tabId?: number;
  readonly url?: string;
}

/**
 * Why the message channel itself failed, as opposed to the handler at the
 * other end. `no-receiver` is the ordinary one: a closed sidebar, a
 * privileged page with no content script, a tab that predates the extension.
 */
export type TransportErrorKind = "no-receiver" | "transport-failed";

export interface TransportError {
  readonly kind: TransportErrorKind;
  readonly message: string;
}
