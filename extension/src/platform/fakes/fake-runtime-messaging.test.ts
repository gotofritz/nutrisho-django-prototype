import { describe, expect, it, vi } from "vitest";

import { createFakeRuntimeMessaging } from "./fake-runtime-messaging";

// The fake is what every test above the platform layer runs against, so it
// has to fail the same way the real transport does. A fake that always
// succeeds would hide exactly the cases messaging has to handle.
describe("fake runtime messaging", () => {
  it("delivers a message to the registered listener and returns its reply", async () => {
    const transport = createFakeRuntimeMessaging();
    transport.onMessage(async () => "pong");

    await expect(transport.send({ type: "ping" })).resolves.toEqual({
      ok: true,
      value: "pong",
    });
  });

  it("reports no listener as no-receiver", async () => {
    await expect(
      createFakeRuntimeMessaging().send({ type: "ping" }),
    ).resolves.toEqual({
      ok: false,
      error: { kind: "no-receiver", message: expect.any(String) },
    });
  });

  it("stops delivering once the subscription is disposed", async () => {
    const transport = createFakeRuntimeMessaging();
    const listener = vi.fn(async () => "pong");
    transport.onMessage(listener)();

    const reply = await transport.send({ type: "ping" });

    expect(listener).not.toHaveBeenCalled();
    expect(reply.ok).toBe(false);
  });

  it("delivers to a connected tab", async () => {
    const transport = createFakeRuntimeMessaging();
    transport.connectTab(7, async () => "from the page");

    await expect(transport.sendToTab(7, { type: "ping" })).resolves.toEqual({
      ok: true,
      value: "from the page",
    });
  });

  it("reports a tab with nothing connected as no-receiver", async () => {
    const transport = createFakeRuntimeMessaging();

    await expect(transport.sendToTab(7, { type: "ping" })).resolves.toEqual({
      ok: false,
      error: { kind: "no-receiver", message: expect.any(String) },
    });
  });

  it("hands the listener the sender it was given", async () => {
    const transport = createFakeRuntimeMessaging();
    const listener = vi.fn(async () => "pong");
    transport.connectTab(7, listener);

    await transport.sendToTab(7, { type: "ping" });

    expect(listener).toHaveBeenCalledWith({ type: "ping" }, { tabId: 7 });
  });
});
