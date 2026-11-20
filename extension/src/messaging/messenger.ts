import { err, isResult, type Result } from "@/core/result";
import type {
  RuntimeMessagingPort,
  TransportReply,
} from "@/platform/runtime-messaging";

import type { Message, MessagingError, Reply } from "./types";

/**
 * Typed sending: the message decides the reply's type, and the
 * reply is always a `Result`, so ignoring failure is a type error.
 */
export interface Messenger {
  send<M extends Message>(message: M): Promise<Reply<M["type"]>>;
  /** Reach a content script. The tab may have none — that is `no-receiver`. */
  sendToTab<M extends Message>(
    tabId: number,
    message: M,
  ): Promise<Reply<M["type"]>>;
}

function describe(raw: unknown): string {
  return raw === null ? "null" : typeof raw;
}

async function unwrap<K extends Message["type"]>(
  transport: Promise<TransportReply>,
): Promise<Reply<K>> {
  const delivered = await transport;
  // A transport failure is already a messaging failure: its kinds are part of
  // `MessagingErrorKind` precisely so it can pass through unchanged.
  if (!delivered.ok) return err(delivered.error);

  const reply = delivered.value;
  if (!isResult(reply)) {
    return err({
      kind: "malformed-reply",
      message: `expected a Result, got ${describe(reply)}`,
    });
  }

  // The far end is this extension's own registry, which only ever replies
  // with `Reply<K>`; anything else has already been rejected above.
  return reply as Result<never, MessagingError> as Reply<K>;
}

export function createMessenger(port: RuntimeMessagingPort): Messenger {
  return {
    send<M extends Message>(message: M): Promise<Reply<M["type"]>> {
      return unwrap<M["type"]>(port.send(message));
    },

    sendToTab<M extends Message>(
      tabId: number,
      message: M,
    ): Promise<Reply<M["type"]>> {
      return unwrap<M["type"]>(port.sendToTab(tabId, message));
    },
  };
}
