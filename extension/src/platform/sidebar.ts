import { browser } from "wxt/browser";

import { err, ok, type Result } from "@/core/result";

/**
 * Where the user gesture happened. Both browsers require the sidebar to be
 * opened from a gesture, and Chrome additionally wants to know what to scope
 * the panel to.
 */
export interface GestureContext {
  readonly tabId?: number;
  readonly windowId?: number;
}

export type SidebarErrorKind =
  /** Neither backing API exists — a browser this extension does not support. */
  | "unsupported"
  /** Chrome's panel is scoped to a tab or a window, and neither was given. */
  | "no-target"
  /** The browser refused: no user gesture, or the window went away. */
  | "open-failed"
  /**
   * The call never settled. Firefox's sidebar is already open for every
   * capture after the first, and what `sidebarAction.open()` does then is
   * not this extension's to rely on — so the caller stops waiting.
   */
  | "open-timed-out";

export interface SidebarError {
  readonly kind: SidebarErrorKind;
  readonly message: string;
}

/**
 * The sidebar, behind one interface for two different APIs: Firefox has
 * `sidebarAction`, Chrome has `sidePanel`.
 *
 * The interface promises only what both can do — open, from a gesture. It
 * deliberately does not promise per-tab scoping, which is Chrome's model
 * alone: Firefox's sidebar is per window and survives tab navigation.
 */
export interface SidebarPort {
  open(fromGesture: GestureContext): Promise<Result<void, SidebarError>>;
}

export interface SidebarActionApi {
  open(): Promise<void>;
}

export interface SidePanelApi {
  open(options: { tabId?: number; windowId?: number }): Promise<void>;
}

export interface SidebarBackings {
  readonly sidebarAction?: SidebarActionApi;
  readonly sidePanel?: SidePanelApi;
}

function failed(cause: unknown): Result<void, SidebarError> {
  return err({
    kind: "open-failed",
    message: cause instanceof Error ? cause.message : String(cause),
  });
}

export function createSidebar(backings: SidebarBackings): SidebarPort {
  return {
    open(fromGesture: GestureContext): Promise<Result<void, SidebarError>> {
      // Not `async`: both browsers require the API call inside the gesture's
      // own task, and an `await` before it would lose the gesture. Everything
      // here up to the call is synchronous, and the capture in
      // `background/capture.ts` depends on it staying that way.
      const { sidebarAction, sidePanel } = backings;

      if (sidebarAction) {
        try {
          return sidebarAction.open().then(() => ok(undefined), failed);
        } catch (cause) {
          return Promise.resolve(failed(cause));
        }
      }

      if (sidePanel) {
        const target =
          fromGesture.tabId != null
            ? { tabId: fromGesture.tabId }
            : fromGesture.windowId != null
              ? { windowId: fromGesture.windowId }
              : undefined;
        if (!target) {
          return Promise.resolve(
            err({
              kind: "no-target",
              message: "sidePanel.open needs a tab or a window to open in",
            }),
          );
        }
        try {
          return sidePanel.open(target).then(() => ok(undefined), failed);
        } catch (cause) {
          return Promise.resolve(failed(cause));
        }
      }

      return Promise.resolve(
        err({
          kind: "unsupported",
          message: "this browser has neither sidebarAction nor sidePanel",
        }),
      );
    },
  };
}

export function createBrowserSidebar(): SidebarPort {
  // `sidebarAction` is Firefox-only and absent from the shared typings, so the
  // structural shape this wrapper needs is asserted rather than derived. The
  // shape itself is covered by `sidebar.test.ts`, against a fake per browser.
  return createSidebar(browser as unknown as SidebarBackings);
}
