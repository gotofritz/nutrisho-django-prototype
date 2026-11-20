import type { PageCapture } from "@/core/capture";
import { createRegistry } from "@/messaging/registry";
import type { RuntimeMessagingPort } from "@/platform/runtime-messaging";

import { extractCapture } from "./extract.dom";

export interface ContentDeps {
  readonly messaging: RuntimeMessagingPort;
  /** Injected so the wiring is testable without a document. */
  readonly extract?: () => PageCapture;
}

/**
 * Wire up the page context and start listening.
 *
 * The content script is absent on privileged pages, on the browser's own
 * add-on listing, in the PDF viewer, and in any tab that predates the
 * extension. That is ordinary: a message sent to a tab without one comes back
 * as `no-receiver`, and the caller acts on it.
 */
export function startContent(deps: ContentDeps): () => void {
  const registry = createRegistry();
  const extract = deps.extract ?? (() => extractCapture({ document, window }));

  registry.on("ping", () => ({ from: "content" }) as const);
  // Only ever in reply to a message, which only ever follows a user gesture:
  // nothing is read off the page until the user asks for a card there.
  registry.on("capture-selection", () => extract());

  return deps.messaging.onMessage((raw, sender) =>
    registry.dispatch(raw, sender),
  );
}
