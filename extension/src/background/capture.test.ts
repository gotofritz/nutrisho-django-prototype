import { describe, expect, it, vi } from "vitest";

import type { PageCapture } from "@/core/capture";
import { clippingFrom } from "@/core/clipping";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { ok } from "@/core/result";
import { createMessenger } from "@/messaging/messenger";
import { createFakeRuntimeMessaging } from "@/platform/fakes/fake-runtime-messaging";
import type { ScriptingPort } from "@/platform/scripting";
import type { SidebarPort } from "@/platform/sidebar";

import { captureFromGesture, describeCapture } from "./capture";

const NOW = new Date("2026-11-20T09:30:00.000Z");

const CAPTURE: PageCapture = {
  text: "2 aubergines\n1 tbsp olive oil",
  title: "Melanzane — Example",
  url: "https://example.test/melanzane",
  warnings: [],
};

function fakeSidebar(): SidebarPort & { calls: number } {
  const sidebar = {
    calls: 0,
    open: vi.fn(async () => {
      sidebar.calls += 1;
      return ok(undefined);
    }),
  };
  return sidebar as unknown as SidebarPort & { calls: number };
}

function fakeScripting(
  inject: ScriptingPort["inject"] = vi.fn(async () => ok(undefined)),
): ScriptingPort {
  return { inject };
}

const refusedInjection = () =>
  fakeScripting(
    vi.fn(async () => ({
      ok: false as const,
      error: {
        kind: "not-injectable" as const,
        message: "cannot access about:reader",
      },
    })),
  );

/** A page whose content script answers, as one already injected would. */
function pageThatAnswers(capture: PageCapture = CAPTURE) {
  const transport = createFakeRuntimeMessaging();
  transport.connectTab(7, async () => ok(capture));
  return transport;
}

function deps(
  overrides: Partial<Parameters<typeof captureFromGesture>[1]> = {},
) {
  return {
    messenger: createMessenger(pageThatAnswers()),
    scripting: fakeScripting(),
    sidebar: fakeSidebar(),
    clippings: createFakeClippingStore(),
    now: () => NOW,
    ...overrides,
  };
}

describe("captureFromGesture", () => {
  it("stores the selection as the clipping", async () => {
    const withDeps = deps();

    const result = await captureFromGesture({ tabId: 7 }, withDeps);

    expect(result).toEqual({
      ok: true,
      value: {
        clipping: clippingFrom(CAPTURE, NOW),
        sidebar: { ok: true, value: undefined },
      },
    });
    expect(await withDeps.clippings.load()).toEqual(
      ok(clippingFrom(CAPTURE, NOW)),
    );
  });

  // Both browsers require `open` inside the gesture's own task, so awaiting
  // the page first forfeits it.
  it("opens the sidebar before it asks the page for anything", () => {
    const sidebar = fakeSidebar();
    const transport = createFakeRuntimeMessaging();
    transport.connectTab(7, async () => {
      expect(sidebar.calls).toBe(1);
      return ok(CAPTURE);
    });

    const pending = captureFromGesture(
      { tabId: 7 },
      deps({ messenger: createMessenger(transport), sidebar }),
    );

    // Synchronously, before anything is awaited.
    expect(sidebar.calls).toBe(1);
    return pending;
  });

  it("injects the content script and retries when the tab has none", async () => {
    const transport = createFakeRuntimeMessaging();
    const inject = vi.fn(async () => {
      transport.connectTab(7, async () => ok(CAPTURE));
      return ok(undefined);
    });

    const result = await captureFromGesture(
      { tabId: 7 },
      deps({
        messenger: createMessenger(transport),
        scripting: fakeScripting(inject),
      }),
    );

    expect(inject).toHaveBeenCalledWith(7);
    expect(result.ok && result.value.clipping.text).toBe(CAPTURE.text);
  });

  // A page no script can run on still gives the menu's own copy of the
  // selection: one line, but better than nothing, and the warning says why.
  it("falls back to the menu's own text when no content script can run", async () => {
    const result = await captureFromGesture(
      {
        tabId: 7,
        selectionText: "2 aubergines 1 tbsp olive oil",
        pageUrl: "https://example.test/melanzane",
      },
      deps({
        messenger: createMessenger(createFakeRuntimeMessaging()),
        scripting: refusedInjection(),
      }),
    );

    expect(result.ok && result.value.clipping).toEqual(
      expect.objectContaining({
        text: "2 aubergines 1 tbsp olive oil",
        url: "https://example.test/melanzane",
      }),
    );
    expect(
      result.ok && result.value.clipping.warnings.map((it) => it.kind),
    ).toEqual(["no-content-script"]);
  });

  it("uses the menu's text when the page could read none, and keeps the warning", async () => {
    const warnings = [
      { kind: "shadow-dom" as const, message: "inside a shadow root" },
    ];

    const result = await captureFromGesture(
      { tabId: 7, selectionText: "2 aubergines" },
      deps({
        messenger: createMessenger(
          pageThatAnswers({ ...CAPTURE, text: "", warnings }),
        ),
      }),
    );

    expect(result.ok && result.value.clipping.text).toBe("2 aubergines");
    expect(result.ok && result.value.clipping.warnings).toEqual(warnings);
  });

  // The toolbar button opens the sidebar whether or not anything is
  // selected: with nothing, the last clipping stays.
  it("stores nothing, and keeps the last clipping, when nothing is selected", async () => {
    const earlier = clippingFrom(
      { ...CAPTURE, text: "basil" },
      new Date("2026-11-19T00:00:00Z"),
    );
    const sidebar = fakeSidebar();
    const withDeps = deps({
      messenger: createMessenger(pageThatAnswers({ ...CAPTURE, text: "" })),
      clippings: createFakeClippingStore(earlier),
      sidebar,
    });

    const result = await captureFromGesture({ tabId: 7 }, withDeps);

    expect(!result.ok && result.error.kind).toBe("nothing-captured");
    expect(sidebar.calls).toBe(1);
    expect(await withDeps.clippings.load()).toEqual(ok(earlier));
  });

  it("says why when no script could read the page and the menu had no text", async () => {
    const result = await captureFromGesture(
      { tabId: 7 },
      deps({
        messenger: createMessenger(createFakeRuntimeMessaging()),
        scripting: refusedInjection(),
      }),
    );

    expect(!result.ok && result.error.kind).toBe("nothing-captured");
    expect(!result.ok && result.error.message).toContain("no content script");
  });

  it("fails when the gesture carried no tab to read", async () => {
    const result = await captureFromGesture({}, deps());

    expect(!result.ok && result.error.kind).toBe("no-tab");
  });

  // The sidebar reads the clipping back out, so an unsaved one is lost.
  it("reports a clipping that could not be stored", async () => {
    const clippings = createFakeClippingStore();
    clippings.failWith({ kind: "write-failed", message: "quota exceeded" });

    const result = await captureFromGesture({ tabId: 7 }, deps({ clippings }));

    expect(!result.ok && result.error.kind).toBe("not-saved");
  });

  it("reports a sidebar that refused to open, with the clipping it still stored", async () => {
    const sidebar = {
      open: vi.fn(async () => ({
        ok: false as const,
        error: { kind: "open-failed" as const, message: "no user gesture" },
      })),
    };

    const result = await captureFromGesture({ tabId: 7 }, deps({ sidebar }));

    expect(result.ok && result.value.sidebar.ok).toBe(false);
    expect(result.ok && result.value.clipping.text).toBe(CAPTURE.text);
  });
});

// Firefox's sidebar is already open for every capture after the first, and
// what `sidebarAction.open()` does then is not this extension's to rely on.
describe("a sidebar that does not finish opening", () => {
  const hanging = { open: () => new Promise<never>(() => {}) };

  it("still stores the clipping, and says it timed out", async () => {
    const withDeps = deps({ sidebar: hanging, sidebarTimeoutMs: 1 });

    const result = await captureFromGesture({ tabId: 7 }, withDeps);

    expect(
      result.ok && !result.value.sidebar.ok && result.value.sidebar.error.kind,
    ).toBe("open-timed-out");
    expect(await withDeps.clippings.load()).toEqual(
      ok(clippingFrom(CAPTURE, NOW)),
    );
  });

  it("does not wait for it before rejecting a gesture with no tab", async () => {
    const result = await captureFromGesture(
      {},
      deps({ sidebar: hanging, sidebarTimeoutMs: 1 }),
    );

    expect(!result.ok && result.error.kind).toBe("no-tab");
  });
});

describe("describeCapture", () => {
  it("reduces a failure to its kind and message", async () => {
    const result = await captureFromGesture({}, deps());

    expect(describeCapture(result)).toEqual({
      outcome: "failed",
      failure: { kind: "no-tab", message: expect.any(String) },
      warnings: [],
    });
  });

  it("reports a success as the blind spots it hit, and a sidebar that failed", async () => {
    const result = await captureFromGesture(
      { tabId: 7 },
      deps({
        messenger: createMessenger(
          pageThatAnswers({
            ...CAPTURE,
            warnings: [{ kind: "selection-truncated", message: "cut" }],
          }),
        ),
        sidebar: {
          open: async () => ({
            ok: false as const,
            error: { kind: "open-failed" as const, message: "no gesture" },
          }),
        },
      }),
    );

    expect(describeCapture(result)).toEqual({
      outcome: "captured",
      warnings: ["selection-truncated"],
      sidebar: { kind: "open-failed", message: "no gesture" },
    });
  });

  // D15: nothing from a page is logged.
  it("carries no page content", async () => {
    const result = await captureFromGesture({ tabId: 7 }, deps());

    const report = JSON.stringify(describeCapture(result));
    expect(report).not.toContain("aubergine");
    expect(report).not.toContain("example.test");
  });
});
