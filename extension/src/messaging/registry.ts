import { err, ok, type Result } from "@/core/result";
import type { MessageSender } from "@/platform/types";

import type {
  MessageOf,
  MessagingError,
  MessageType,
  ResponseOf,
} from "./types";

export type Handler<K extends MessageType> = (
  message: MessageOf<K>,
  sender: MessageSender,
) => ResponseOf<K> | Promise<ResponseOf<K>>;

export interface HandlerRegistry {
  on<K extends MessageType>(type: K, handler: Handler<K>): void;
  /**
   * Turn an incoming, untrusted value into a reply. Never throws: the whole
   * point is that a failure at this end reaches the sender as data.
   */
  dispatch(
    raw: unknown,
    sender: MessageSender,
  ): Promise<Result<unknown, MessagingError>>;
}

function describe(raw: unknown): string {
  if (raw === null) return "null";
  if (typeof raw !== "object") return typeof raw;
  const type = (raw as { type?: unknown }).type;
  return typeof type === "string" ? `"${type}"` : "an object with no type";
}

function messageType(raw: unknown): MessageType | undefined {
  if (typeof raw !== "object" || raw === null) return undefined;
  const type = (raw as { type?: unknown }).type;
  return typeof type === "string" ? (type as MessageType) : undefined;
}

/**
 * One map holds handlers for every member of the union, so it is typed at the
 * union rather than at each `K`. `on` narrows on the way in and `dispatch`
 * has already matched the message to its type on the way out.
 */
type RegisteredHandler = (
  message: MessageOf<MessageType>,
  sender: MessageSender,
) => unknown;

export function createRegistry(): HandlerRegistry {
  const handlers = new Map<MessageType, RegisteredHandler>();

  return {
    on<K extends MessageType>(type: K, handler: Handler<K>): void {
      // Two handlers for one type is a wiring bug, and the silent version of
      // it — last registration wins — is the expensive kind to find.
      if (handlers.has(type)) {
        throw new Error(`a handler is already registered for "${type}"`);
      }
      handlers.set(type, handler as RegisteredHandler);
    },

    async dispatch(
      raw: unknown,
      sender: MessageSender,
    ): Promise<Result<unknown, MessagingError>> {
      const type = messageType(raw);
      const handler = type ? handlers.get(type) : undefined;

      // Anything on the page, and any other extension, can send this context
      // a message. Dropping what we do not recognise is how a typo in a
      // message type becomes an afternoon of debugging.
      if (!handler) {
        return err({
          kind: "unknown-message",
          message: `no handler for ${describe(raw)}`,
        });
      }

      try {
        return ok(await handler(raw as MessageOf<MessageType>, sender));
      } catch (cause) {
        return err({
          kind: "handler-failed",
          message: cause instanceof Error ? cause.message : String(cause),
        });
      }
    },
  };
}
