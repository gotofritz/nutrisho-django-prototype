import type {
  CaptureWarning,
  CaptureWarningKind,
  PageCapture,
} from "@/core/capture";
import { warn } from "@/core/capture";
import { clippingFrom, type Clipping } from "@/core/clipping";
import type { ClippingStore } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";
import type { Messenger } from "@/messaging/messenger";
import type { ScriptingPort } from "@/platform/scripting";
import type { SidebarError, SidebarPort } from "@/platform/sidebar";

/**
 * One user gesture, from the click to a stored clipping (plan 012, M6).
 * Copied from anklipper, where the end of it is a card draft.
 *
 * The gesture is the menu entry, the keyboard shortcut or the toolbar button;
 * all three arrive here as a `CaptureTrigger`, so there is one path to test
 * and one path to get wrong.
 */
export interface CaptureTrigger {
  readonly tabId?: number;
  /**
   * The browser's own copy of the selection, from the menu event. One line
   * and plain, and used only when the page itself cannot be read.
   */
  readonly selectionText?: string;
  readonly pageUrl?: string;
}

/**
 * How long the sidebar gets to answer before the capture stops waiting on it.
 * Nothing depends on the answer except the report: the clipping is stored either
 * way, and a sidebar the user can open themselves is a far smaller problem
 * than a capture that produced nothing.
 */
export const SIDEBAR_OPEN_TIMEOUT_MS = 1_000;

export interface CaptureDeps {
  readonly messenger: Messenger;
  readonly scripting: ScriptingPort;
  readonly sidebar: SidebarPort;
  readonly clippings: ClippingStore;
  readonly now?: () => Date;
  /** Injected so the timeout is testable without waiting for it. */
  readonly sidebarTimeoutMs?: number;
}

export type CaptureFailureKind =
  /** The gesture named no tab — nothing to read. */
  | "no-tab"
  /** Neither the page nor the event carried any text. */
  | "nothing-captured"
  /** The clipping could not be stored, so the sidebar cannot read it. */
  | "not-saved";

export interface CaptureFailure {
  readonly kind: CaptureFailureKind;
  readonly message: string;
}

export interface CaptureOutcome {
  readonly clipping: Clipping;
  /**
   * Whether the sidebar opened. Kept rather than thrown: the clipping is
   * stored either way, and a sidebar the user can open themselves is a
   * smaller problem than a capture that produced nothing.
   */
  readonly sidebar: Result<void, SidebarError>;
}

function fromTrigger(
  trigger: CaptureTrigger,
  warnings: readonly CaptureWarning[],
): PageCapture {
  return {
    text: trigger.selectionText ?? "",
    title: "",
    url: trigger.pageUrl ?? "",
    warnings,
  };
}

/**
 * Ask the page. A tab with no content script is the ordinary case rather than
 * an error: it predates the extension, or the user never triggered a capture
 * in it. So the first `no-receiver` buys one injection and one retry.
 */
async function readPage(
  tabId: number,
  deps: CaptureDeps,
): Promise<Result<PageCapture, CaptureWarning>> {
  const first = await deps.messenger.sendToTab(tabId, {
    type: "capture-selection",
  });
  if (first.ok) return ok(first.value);
  if (first.error.kind !== "no-receiver") {
    return err(warn("no-content-script", first.error.message));
  }

  const injected = await deps.scripting.inject(tabId);
  if (!injected.ok) {
    return err(warn("no-content-script", injected.error.message));
  }

  const second = await deps.messenger.sendToTab(tabId, {
    type: "capture-selection",
  });
  return second.ok
    ? ok(second.value)
    : err(warn("no-content-script", second.error.message));
}

/**
 * Handle one gesture.
 *
 * Deliberately not `async`: the sidebar has to be opened inside the gesture's
 * own task, and an `await` in front of that call forfeits the gesture on both
 * browsers. Everything before `sidebar.open` here is synchronous, and a test
 * holds it that way.
 */
export function captureFromGesture(
  trigger: CaptureTrigger,
  deps: CaptureDeps,
): Promise<Result<CaptureOutcome, CaptureFailure>> {
  const opening = deps.sidebar.open({ tabId: trigger.tabId });

  return finish(trigger, deps, opening);
}

/**
 * Settle, or give up and say so. A promise that never settles would otherwise
 * take the whole capture down with it.
 */
function withTimeout(
  opening: Promise<Result<void, SidebarError>>,
  ms: number,
): Promise<Result<void, SidebarError>> {
  return new Promise((resolve) => {
    const timer = setTimeout(
      () =>
        resolve(
          err({
            kind: "open-timed-out",
            message: `the sidebar did not answer within ${ms}ms`,
          }),
        ),
      ms,
    );

    void opening.then(
      (result) => {
        clearTimeout(timer);
        resolve(result);
      },
      (cause: unknown) => {
        clearTimeout(timer);
        resolve(
          err({
            kind: "open-failed",
            message: cause instanceof Error ? cause.message : String(cause),
          }),
        );
      },
    );
  });
}

async function finish(
  trigger: CaptureTrigger,
  deps: CaptureDeps,
  opening: Promise<Result<void, SidebarError>>,
): Promise<Result<CaptureOutcome, CaptureFailure>> {
  if (trigger.tabId === undefined) {
    return err({
      kind: "no-tab",
      message: "the gesture named no tab to capture from",
    });
  }

  const read = await readPage(trigger.tabId, deps);
  const capture = read.ok ? read.value : fromTrigger(trigger, [read.error]);

  // A blind spot still makes a clipping when the menu carried text: a
  // degraded clipping beats none, provided the warning says so.
  const filled =
    capture.text === "" && (trigger.selectionText ?? "") !== ""
      ? { ...capture, text: trigger.selectionText as string }
      : capture;

  // Nothing selected is ordinary from the toolbar button: the sidebar opens
  // and the last clipping stays.
  if (filled.text.trim() === "") {
    return err({
      kind: "nothing-captured",
      message: read.ok
        ? "nothing was selected on the page"
        : `no content script could read this page: ${read.error.message}`,
    });
  }

  // The background is unloaded when idle, so the clipping is durable from
  // the moment it exists, and the sidebar reads it back out rather than being
  // handed it.
  const clipping = clippingFrom(filled, (deps.now ?? (() => new Date()))());
  const saved = await deps.clippings.save(clipping);
  if (!saved.ok) {
    return err({
      kind: "not-saved",
      message: `the clipping could not be stored: ${saved.error.message}`,
    });
  }

  // Only now, with the clipping stored, is the sidebar's answer worth waiting
  // for, and even then not indefinitely.
  const sidebar = await withTimeout(
    opening,
    deps.sidebarTimeoutMs ?? SIDEBAR_OPEN_TIMEOUT_MS,
  );

  return ok({ clipping, sidebar });
}

/**
 * What a capture is worth saying out loud, in development.
 *
 * Deliberately not the clipping: a report is for a console and for an issue,
 * so it carries kinds and our own messages and no page content whatsoever
 * (D15). A test pins that.
 */
export interface CaptureReport {
  readonly outcome: "captured" | "failed";
  readonly failure?: CaptureFailure;
  readonly warnings: readonly CaptureWarningKind[];
  readonly sidebar?: SidebarError;
}

export function describeCapture(
  result: Result<CaptureOutcome, CaptureFailure>,
): CaptureReport {
  if (!result.ok) {
    return { outcome: "failed", failure: result.error, warnings: [] };
  }

  const { clipping, sidebar } = result.value;
  return {
    outcome: "captured",
    warnings: clipping.warnings.map((warning) => warning.kind),
    ...(sidebar.ok ? {} : { sidebar: sidebar.error }),
  };
}
