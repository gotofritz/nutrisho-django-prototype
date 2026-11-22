import { describe, expect, it, vi } from "vitest";

import { createRegistry } from "./registry";

describe("handler registry", () => {
  it("routes a message to the handler registered for its type", async () => {
    const registry = createRegistry();
    registry.on("ping", () => ({ from: "background" }));

    await expect(registry.dispatch({ type: "ping" }, {})).resolves.toEqual({
      ok: true,
      value: { from: "background" },
    });
  });

  it("hands the handler the message and the sender", async () => {
    const registry = createRegistry();
    const handler = vi.fn(() => ({ from: "background" }) as const);
    registry.on("ping", handler);

    await registry.dispatch({ type: "ping" }, { tabId: 7 });

    expect(handler).toHaveBeenCalledWith({ type: "ping" }, { tabId: 7 });
  });

  it("awaits an asynchronous handler", async () => {
    const registry = createRegistry();
    registry.on("ping", async () => ({ from: "content" }) as const);

    await expect(registry.dispatch({ type: "ping" }, {})).resolves.toEqual({
      ok: true,
      value: { from: "content" },
    });
  });

  // Anything on the page or in another extension can send this context a
  // message. Dropping what we do not recognise silently is how a typo in a
  // message type becomes an afternoon of debugging.
  it("rejects a type with no handler as unknown-message", async () => {
    const reply = await createRegistry().dispatch({ type: "ping" }, {});

    expect(reply).toEqual({
      ok: false,
      error: {
        kind: "unknown-message",
        message: expect.stringContaining("ping"),
      },
    });
  });

  it.each([
    ["a bare string", "ping"],
    ["null", null],
    ["undefined", undefined],
    ["an object with no type", { payload: 1 }],
    ["an object whose type is not a string", { type: 7 }],
  ])("rejects %s as unknown-message", async (_label, raw) => {
    const registry = createRegistry();
    registry.on("ping", () => ({ from: "background" }));

    const reply = await registry.dispatch(raw, {});

    expect(reply.ok).toBe(false);
    expect(reply.ok === false && reply.error.kind).toBe("unknown-message");
  });

  it("converts a handler that throws into a failure reply", async () => {
    const registry = createRegistry();
    registry.on("ping", () => {
      throw new Error("handler exploded");
    });

    await expect(registry.dispatch({ type: "ping" }, {})).resolves.toEqual({
      ok: false,
      error: { kind: "handler-failed", message: "handler exploded" },
    });
  });

  it("converts a handler that rejects into a failure reply", async () => {
    const registry = createRegistry();
    registry.on("ping", async () => {
      throw new Error("handler exploded");
    });

    await expect(registry.dispatch({ type: "ping" }, {})).resolves.toEqual({
      ok: false,
      error: { kind: "handler-failed", message: "handler exploded" },
    });
  });

  it("refuses a second handler for the same type rather than replacing the first", () => {
    const registry = createRegistry();
    registry.on("ping", () => ({ from: "background" }));

    expect(() => registry.on("ping", () => ({ from: "content" }))).toThrow(
      /ping/,
    );
  });
});
