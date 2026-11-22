import { browser } from "wxt/browser";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createRuntimeMessaging } from "./runtime-messaging";

describe("runtime messaging transport", () => {
  it("delivers a message to a registered listener and returns its reply", async () => {
    const transport = createRuntimeMessaging();
    transport.onMessage(async () => ({ ok: true, value: "pong" }));

    const reply = await transport.send({ type: "ping" });

    expect(reply).toEqual({ ok: true, value: { ok: true, value: "pong" } });
  });

  it("hands the listener the message and the sender", async () => {
    const transport = createRuntimeMessaging();
    const listener = vi.fn(async () => ({ ok: true, value: null }));
    transport.onMessage(listener);

    await transport.send({ type: "ping" });

    expect(listener).toHaveBeenCalledWith({ type: "ping" }, expect.any(Object));
  });

  it("stops delivering once the subscription is disposed", async () => {
    const transport = createRuntimeMessaging();
    const listener = vi.fn(async () => ({ ok: true, value: null }));
    const dispose = transport.onMessage(listener);

    dispose();
    await transport.send({ type: "ping" });

    expect(listener).not.toHaveBeenCalled();
  });

  // A closed sidebar, a privileged page, a tab that predates the extension:
  // all of them are ordinary, and none of them may reach the caller as an
  // unhandled rejection.
  it("reports a context with no listener as no-receiver", async () => {
    const reply = await createRuntimeMessaging().send({ type: "ping" });

    expect(reply).toEqual({
      ok: false,
      error: { kind: "no-receiver", message: expect.any(String) },
    });
  });

  it("reports any other transport rejection as transport-failed", async () => {
    const transport = createRuntimeMessaging();
    transport.onMessage(async () => ({ ok: true, value: null }));
    vi.spyOn(browser.runtime, "sendMessage").mockRejectedValueOnce(
      new Error("Extension context invalidated."),
    );

    const reply = await transport.send({ type: "ping" });

    expect(reply).toEqual({
      ok: false,
      error: {
        kind: "transport-failed",
        message: "Extension context invalidated.",
      },
    });
  });
});

// The fake browser leaves `tabs.sendMessage` unimplemented; this is the
// promise-returning half of its overload, which is the half the wrapper uses.
const sendToTab =
  vi.fn<(tabId: number, message: unknown) => Promise<unknown>>();

describe("runtime messaging to a tab", () => {
  beforeEach(() => {
    sendToTab.mockReset();
    browser.tabs.sendMessage =
      sendToTab as unknown as typeof browser.tabs.sendMessage;
  });

  it("returns the tab's reply", async () => {
    sendToTab.mockResolvedValue({
      ok: true,
      value: "pong",
    });

    const reply = await createRuntimeMessaging().sendToTab(7, { type: "ping" });

    expect(sendToTab).toHaveBeenCalledWith(7, { type: "ping" });
    expect(reply).toEqual({ ok: true, value: { ok: true, value: "pong" } });
  });

  it("reports a tab with no content script as no-receiver", async () => {
    sendToTab.mockRejectedValue(
      new Error(
        "Could not establish connection. Receiving end does not exist.",
      ),
    );

    const reply = await createRuntimeMessaging().sendToTab(7, { type: "ping" });

    expect(reply.ok).toBe(false);
    expect(reply.ok === false && reply.error.kind).toBe("no-receiver");
  });

  it("reports a listener that answered with nothing as no-receiver", async () => {
    sendToTab.mockResolvedValue(undefined);

    const reply = await createRuntimeMessaging().sendToTab(7, { type: "ping" });

    expect(reply.ok === false && reply.error.kind).toBe("no-receiver");
  });
});
