import { describe, expect, it } from "vitest";

import { createFakeRuntimeMessaging } from "@/platform/fakes/fake-runtime-messaging";

import { createMessenger } from "./messenger";
import { createRegistry } from "./registry";

function backgroundAnswering(from: "background" | "content") {
  const transport = createFakeRuntimeMessaging();
  const registry = createRegistry();
  registry.on("ping", () => ({ from }) as const);
  transport.onMessage((raw, sender) => registry.dispatch(raw, sender));
  return transport;
}

describe("messenger", () => {
  it("carries a reply back from the handler that answered it", async () => {
    const messenger = createMessenger(backgroundAnswering("background"));

    await expect(messenger.send({ type: "ping" })).resolves.toEqual({
      ok: true,
      value: { from: "background" },
    });
  });

  it("carries a handler failure back as a failure", async () => {
    const transport = createFakeRuntimeMessaging();
    const registry = createRegistry();
    transport.onMessage((raw, sender) => registry.dispatch(raw, sender));

    await expect(
      createMessenger(transport).send({ type: "ping" }),
    ).resolves.toEqual({
      ok: false,
      error: {
        kind: "unknown-message",
        message: expect.stringContaining("ping"),
      },
    });
  });

  // The sidebar is closed, the tab predates the extension, the page is
  // privileged: all the same to the caller, and none of them a crash.
  it("reports a context with nothing listening as no-receiver", async () => {
    const messenger = createMessenger(createFakeRuntimeMessaging());

    await expect(messenger.send({ type: "ping" })).resolves.toEqual({
      ok: false,
      error: { kind: "no-receiver", message: expect.any(String) },
    });
  });

  it("reaches a content script through its tab", async () => {
    const transport = createFakeRuntimeMessaging();
    const registry = createRegistry();
    registry.on("ping", () => ({ from: "content" }) as const);
    transport.connectTab(7, (raw, sender) => registry.dispatch(raw, sender));

    await expect(
      createMessenger(transport).sendToTab(7, { type: "ping" }),
    ).resolves.toEqual({ ok: true, value: { from: "content" } });
  });

  it("reports a tab with no content script as no-receiver", async () => {
    const messenger = createMessenger(createFakeRuntimeMessaging());

    const reply = await messenger.sendToTab(7, { type: "ping" });

    expect(reply.ok === false && reply.error.kind).toBe("no-receiver");
  });

  // Something answered, but not with the Result every handler owes —
  // another extension, or an older build of this one.
  it("reports a reply that is not Result-shaped as malformed-reply", async () => {
    const transport = createFakeRuntimeMessaging();
    transport.onMessage(async () => "pong");

    await expect(
      createMessenger(transport).send({ type: "ping" }),
    ).resolves.toEqual({
      ok: false,
      error: { kind: "malformed-reply", message: expect.any(String) },
    });
  });
});
