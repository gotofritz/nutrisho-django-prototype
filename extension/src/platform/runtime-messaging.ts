import { browser } from "wxt/browser";

import { err, ok, type Result } from "@/core/result";

import type { MessageSender, TransportError } from "./types";

/** What came back over the channel, before anyone checks it is a reply. */
export type TransportReply = Result<unknown, TransportError>;

export type TransportListener = (
  message: unknown,
  sender: MessageSender,
) => Promise<unknown>;

/**
 * The message channel itself: delivery and failure, with no opinion
 * about what a message means. `src/messaging/` is the typed layer above it.
 */
export interface RuntimeMessagingPort {
  send(message: unknown): Promise<TransportReply>;
  sendToTab(tabId: number, message: unknown): Promise<TransportReply>;
  onMessage(listener: TransportListener): () => void;
}

/**
 * Both browsers word it differently, and the fake differently again, but all
 * three mean the same thing: nothing was listening.
 */
const NO_RECEIVER =
  /receiving end does not exist|could not establish connection|no listeners available|message port closed/i;

function classify(cause: unknown): TransportError {
  const message = cause instanceof Error ? cause.message : String(cause);
  return NO_RECEIVER.test(message)
    ? { kind: "no-receiver", message }
    : { kind: "transport-failed", message };
}

/**
 * A listener that answered leaves a reply; `undefined` means none did.
 * Every handler in this extension replies with a `Result`, so there is no
 * legitimate `undefined` to confuse with a closed sidebar.
 */
function toReply(raw: unknown): TransportReply {
  return raw === undefined
    ? err({ kind: "no-receiver", message: "no context answered the message" })
    : ok(raw);
}

async function attempt(send: () => Promise<unknown>): Promise<TransportReply> {
  try {
    return toReply(await send());
  } catch (cause) {
    return err(classify(cause));
  }
}

export function createRuntimeMessaging(): RuntimeMessagingPort {
  return {
    send(message: unknown): Promise<TransportReply> {
      return attempt(() => browser.runtime.sendMessage(message));
    },

    sendToTab(tabId: number, message: unknown): Promise<TransportReply> {
      return attempt(() => browser.tabs.sendMessage(tabId, message));
    },

    onMessage(listener: TransportListener): () => void {
      // `return true` plus `sendResponse` rather than returning a promise:
      // Firefox accepts both, Chrome MV3 accepts only this one.
      const wrapped = (
        message: unknown,
        sender: { tab?: { id?: number }; url?: string },
        sendResponse: (response?: unknown) => void,
      ) => {
        void listener(message, { tabId: sender.tab?.id, url: sender.url }).then(
          sendResponse,
        );
        return true;
      };
      browser.runtime.onMessage.addListener(wrapped);
      return () => browser.runtime.onMessage.removeListener(wrapped);
    },
  };
}
