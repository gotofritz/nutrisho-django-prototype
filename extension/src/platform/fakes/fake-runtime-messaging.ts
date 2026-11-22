import { err, ok } from "@/core/result";

import type {
  RuntimeMessagingPort,
  TransportListener,
  TransportReply,
} from "../runtime-messaging";

export interface FakeRuntimeMessaging extends RuntimeMessagingPort {
  /** Put a listener behind a tab id, the way a content script sits behind one. */
  connectTab(tabId: number, listener: TransportListener): () => void;
}

function noReceiver(where: string): TransportReply {
  return err({
    kind: "no-receiver",
    message: `nothing is listening in ${where}`,
  });
}

/**
 * An in-memory `RuntimeMessagingPort`. Every test above the platform layer
 * runs against this rather than the browser, so it has to fail the same way
 * the real transport does — a fake that always succeeds would hide the cases
 * messaging has to handle.
 */
export function createFakeRuntimeMessaging(): FakeRuntimeMessaging {
  let runtimeListener: TransportListener | undefined;
  const tabListeners = new Map<number, TransportListener>();

  return {
    async send(message: unknown): Promise<TransportReply> {
      if (!runtimeListener) return noReceiver("this extension");
      return ok(await runtimeListener(message, {}));
    },

    async sendToTab(tabId: number, message: unknown): Promise<TransportReply> {
      const listener = tabListeners.get(tabId);
      if (!listener) return noReceiver(`tab ${tabId}`);
      return ok(await listener(message, { tabId }));
    },

    onMessage(listener: TransportListener): () => void {
      runtimeListener = listener;
      return () => {
        if (runtimeListener === listener) runtimeListener = undefined;
      };
    },

    connectTab(tabId: number, listener: TransportListener): () => void {
      tabListeners.set(tabId, listener);
      return () => tabListeners.delete(tabId);
    },
  };
}
