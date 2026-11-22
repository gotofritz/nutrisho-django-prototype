import { describe, expect, it, vi } from "vitest";

import type { PageCapture } from "@/core/capture";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { ok } from "@/core/result";
import { CAPTURE_COMMAND } from "@/manifest/manifest";
import { createMessenger } from "@/messaging/messenger";
import type { ActionClick } from "@/platform/action";
import type { CommandInvocation } from "@/platform/commands";
import type { ContextMenuClick } from "@/platform/context-menus";
import { createFakeRuntimeMessaging } from "@/platform/fakes/fake-runtime-messaging";

import type { CaptureReport } from "./capture";
import { CAPTURE_MENU_ITEM, startBackground } from "./start";

/** The submenu entry that sends the text to the ingredients. */
const GROUP_ITEM = `${CAPTURE_MENU_ITEM}-group`;

const CAPTURE: PageCapture = {
  text: "2 aubergines\n1 tbsp olive oil",
  title: "Melanzane — Example",
  url: "https://example.test/melanzane",
  warnings: [],
};

function harness(overrides: Record<string, unknown> = {}) {
  const transport = createFakeRuntimeMessaging();
  transport.connectTab(7, async () => ok(CAPTURE));

  const clicks: ((click: ContextMenuClick) => void)[] = [];
  const commands: ((invocation: CommandInvocation) => void)[] = [];
  const buttons: ((click: ActionClick) => void)[] = [];
  const menus = {
    created: [] as unknown[],
    create: vi.fn(async (item: unknown) => {
      menus.created.push(item);
    }),
    removeAll: vi.fn(async () => {}),
    onClicked: vi.fn((listener: (click: ContextMenuClick) => void) => {
      clicks.push(listener);
      return () => {};
    }),
  };

  const deps = {
    messaging: transport,
    menus,
    commands: {
      onCommand: vi.fn((listener: (invocation: CommandInvocation) => void) => {
        commands.push(listener);
        return () => {};
      }),
    },
    action: {
      onClicked: vi.fn((listener: (click: ActionClick) => void) => {
        buttons.push(listener);
        return () => {};
      }),
    },
    scripting: { inject: vi.fn(async () => ok(undefined)) },
    sidebar: { open: vi.fn(async () => ok(undefined)) },
    clippings: createFakeClippingStore(),
    now: () => new Date("2026-11-20T09:30:00.000Z"),
    ...overrides,
  };

  return { transport, deps, menus, clicks, commands, buttons };
}

async function clipped(deps: ReturnType<typeof harness>["deps"]) {
  const stored = await deps.clippings.load();
  return stored.ok ? stored.value?.text : undefined;
}

async function target(deps: ReturnType<typeof harness>["deps"]) {
  const stored = await deps.clippings.load();
  return stored.ok ? stored.value?.target : undefined;
}

describe("background", () => {
  it("answers a ping once it has started", async () => {
    const { transport, deps } = harness();
    startBackground(deps);

    await expect(
      createMessenger(transport).send({ type: "ping" }),
    ).resolves.toEqual({ ok: true, value: { from: "background" } });
  });

  it("stops answering once it is stopped", async () => {
    const { transport, deps } = harness();

    startBackground(deps)();

    const reply = await createMessenger(transport).send({ type: "ping" });
    expect(reply.ok === false && reply.error.kind).toBe("no-receiver");
  });

  // Shown only on a selection: there is nothing to clip without one. The
  // submenu says where the text goes, as well as to the clipboard.
  it("registers a submenu, on selections only", async () => {
    const { deps, menus } = harness();

    startBackground(deps);
    await vi.waitFor(() => expect(menus.created).toHaveLength(7));

    expect(menus.removeAll).toHaveBeenCalled();
    expect(menus.created).toEqual([
      {
        id: CAPTURE_MENU_ITEM,
        title: "Clip into Nutrisho",
        contexts: ["selection"],
      },
      ...[
        ["name", "Title"],
        ["blurb", "Blurb"],
        ["group", "Ingredient group"],
        ["ingredient", "Ingredient"],
        ["steps", "Steps"],
        ["clipboard", "Clipboard"],
      ].map(([to, title]) => ({
        id: `${CAPTURE_MENU_ITEM}-${to}`,
        parentId: CAPTURE_MENU_ITEM,
        title,
        contexts: ["selection"],
      })),
    ]);
  });

  it.each(["name", "blurb", "group", "ingredient", "steps", "clipboard"])(
    "clips to %s from its submenu entry",
    async (to) => {
      const { deps, clicks } = harness();
      startBackground(deps);

      clicks.forEach((click) =>
        click({ menuItemId: `${CAPTURE_MENU_ITEM}-${to}`, tabId: 7 }),
      );

      await vi.waitFor(async () => expect(await target(deps)).toBe(to));
      expect(await clipped(deps)).toBe(CAPTURE.text);
    },
  );

  it("ignores a click on somebody else's menu entry", async () => {
    const { deps, clicks } = harness();
    startBackground(deps);

    clicks.forEach((click) => click({ menuItemId: "someone-else", tabId: 7 }));

    expect(await clipped(deps)).toBeUndefined();
    expect(deps.sidebar.open).not.toHaveBeenCalled();
  });

  it("clips on the keyboard shortcut", async () => {
    const { deps, commands } = harness();
    startBackground(deps);

    commands.forEach((command) =>
      command({ command: CAPTURE_COMMAND, tabId: 7 }),
    );

    await vi.waitFor(async () =>
      expect(await clipped(deps)).toBe(CAPTURE.text),
    );
    expect(await target(deps)).toBe("clipboard");
  });

  it("ignores somebody else's shortcut", () => {
    const { deps, commands } = harness();
    startBackground(deps);

    commands.forEach((command) => command({ command: "other", tabId: 7 }));

    expect(deps.sidebar.open).not.toHaveBeenCalled();
  });

  // Plan 012, M6: the toolbar button opens the sidebar, and clips the
  // selection if there is one.
  it("clips on the toolbar button", async () => {
    const { deps, buttons } = harness();
    startBackground(deps);

    buttons.forEach((button) => button({ tabId: 7 }));

    await vi.waitFor(async () =>
      expect(await clipped(deps)).toBe(CAPTURE.text),
    );
    expect(await target(deps)).toBe("clipboard");
  });

  // Both browsers require `sidebar.open` inside the gesture's own task. The
  // capture holds that line; this holds the wiring in front of it, where an
  // `await` would be easy to add and impossible to typecheck.
  it.each(["menu", "shortcut", "button"])(
    "opens the sidebar synchronously, inside the %s's gesture",
    (gesture) => {
      const { deps, clicks, commands, buttons } = harness();
      startBackground(deps);

      if (gesture === "menu") {
        clicks.forEach((click) => click({ menuItemId: GROUP_ITEM, tabId: 7 }));
      } else if (gesture === "shortcut") {
        commands.forEach((command) =>
          command({ command: CAPTURE_COMMAND, tabId: 7 }),
        );
      } else {
        buttons.forEach((button) => button({ tabId: 7 }));
      }

      expect(deps.sidebar.open).toHaveBeenCalledTimes(1);
    },
  );
});

describe("reporting what a capture did", () => {
  it("reports every capture, and why one failed", async () => {
    const report = vi.fn<(report: CaptureReport) => void>();
    const { deps, buttons } = harness({ report });
    startBackground(deps);

    buttons.forEach((button) => button({}));

    await vi.waitFor(() =>
      expect(report).toHaveBeenCalledWith(
        expect.objectContaining({
          outcome: "failed",
          failure: expect.objectContaining({ kind: "no-tab" }),
        }),
      ),
    );
  });

  it("clips fine with nobody listening for reports", async () => {
    const { deps, buttons } = harness();
    startBackground(deps);

    buttons.forEach((button) => button({ tabId: 7 }));

    await vi.waitFor(async () =>
      expect(await clipped(deps)).toBe(CAPTURE.text),
    );
    expect(await target(deps)).toBe("clipboard");
  });
});
