import type { ClipTarget } from "@/core/clipping";
import type { ClippingStore } from "@/core/ports/types";
import { CAPTURE_COMMAND, CAPTURE_TITLE } from "@/manifest/manifest";
import { createMessenger } from "@/messaging/messenger";
import { createRegistry } from "@/messaging/registry";
import type { ActionPort } from "@/platform/action";
import type { CommandsPort } from "@/platform/commands";
import type { ContextMenusPort } from "@/platform/context-menus";
import type { RuntimeMessagingPort } from "@/platform/runtime-messaging";
import type { ScriptingPort } from "@/platform/scripting";
import type { SidebarPort } from "@/platform/sidebar";

import type { CaptureReport, CaptureTrigger } from "./capture";
import { captureFromGesture, describeCapture } from "./capture";

/** The menu entry's id; its submenu entries are this plus their target. */
export const CAPTURE_MENU_ITEM = CAPTURE_COMMAND;

/** The submenu, in order: where the text goes, as well as to the clipboard. */
const SUBMENU: readonly { target: ClipTarget; title: string }[] = [
  { target: "name", title: "Title" },
  { target: "blurb", title: "Blurb" },
  { target: "group", title: "Ingredient group" },
  { target: "ingredient", title: "Ingredient" },
  { target: "steps", title: "Steps" },
  { target: "clipboard", title: "Clipboard" },
];

const menuItem = (target: ClipTarget) => `${CAPTURE_MENU_ITEM}-${target}`;

export interface BackgroundDeps {
  readonly messaging: RuntimeMessagingPort;
  readonly menus: ContextMenusPort;
  readonly commands: CommandsPort;
  readonly action: ActionPort;
  readonly scripting: ScriptingPort;
  readonly sidebar: SidebarPort;
  readonly clippings: ClippingStore;
  readonly now?: () => Date;
  /**
   * Told what each capture did. A failed capture stores nothing, so without
   * this it reaches a developer as a sidebar that appears to do nothing. The
   * report carries no page content: see `describeCapture`.
   */
  readonly report?: (report: CaptureReport) => void;
}

/**
 * Wire up the background context and start listening (plan 012, M6; from
 * anklipper).
 *
 * Nothing is kept in module scope: Firefox's event page and Chrome's service
 * worker are both unloaded when idle, so this runs again on every wake-up and
 * anything durable belongs in a store. The menu is therefore registered again
 * on every start, which is why it is removed first.
 *
 * Returns the function that stops it again, which is what the tests use.
 */
export function startBackground(deps: BackgroundDeps): () => void {
  const registry = createRegistry();
  const messenger = createMessenger(deps.messaging);

  registry.on("ping", () => ({ from: "background" }) as const);

  const capture = async (trigger: CaptureTrigger) => {
    const result = await captureFromGesture(trigger, {
      messenger,
      scripting: deps.scripting,
      sidebar: deps.sidebar,
      clippings: deps.clippings,
      ...(deps.now === undefined ? {} : { now: deps.now }),
    });

    deps.report?.(describeCapture(result));
  };

  // Not awaited: each handler has to reach `sidebar.open` inside the
  // gesture's own task, and none of these APIs waits for the promise.
  const stopClicks = deps.menus.onClicked((click) => {
    const entry = SUBMENU.find(
      ({ target }) => menuItem(target) === click.menuItemId,
    );
    if (entry === undefined) return;
    void capture({ ...click, target: entry.target });
  });

  const stopCommands = deps.commands.onCommand((invocation) => {
    if (invocation.command !== CAPTURE_COMMAND) return;
    void capture(invocation);
  });

  // The toolbar button: the sidebar opens, and a selection, if any, is clipped.
  const stopButton = deps.action.onClicked((click) => {
    void capture(click);
  });

  void registerMenu(deps);

  const stopMessages = deps.messaging.onMessage((raw, sender) =>
    registry.dispatch(raw, sender),
  );

  return () => {
    stopMessages();
    stopClicks();
    stopCommands();
    stopButton();
  };
}

/** Shown only on a selection: there is nothing to clip without one. */
async function registerMenu(deps: BackgroundDeps): Promise<void> {
  await deps.menus.removeAll();
  await deps.menus.create({
    id: CAPTURE_MENU_ITEM,
    title: CAPTURE_TITLE,
    contexts: ["selection"],
  });
  for (const { target, title } of SUBMENU) {
    await deps.menus.create({
      id: menuItem(target),
      parentId: CAPTURE_MENU_ITEM,
      title,
      contexts: ["selection"],
    });
  }
}
