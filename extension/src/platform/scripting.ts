import { browser } from "wxt/browser";

import { err, ok, type Result } from "@/core/result";

/**
 * Where WXT emits the content-script entrypoint. The script is registered at
 * runtime rather than in the manifest — a declared one needs match patterns,
 * and those become install-time host permissions the ceiling does not allow —
 * so the path is what injection asks for by name.
 */
export const CONTENT_SCRIPT_FILE = "/content-scripts/content.js";

export type ScriptingErrorKind =
  /** The tab is gone: closed, or navigated before the gesture was handled. */
  | "no-tab"
  /**
   * The page refuses injection. Ordinary rather than exceptional: `about:`
   * and `chrome://` pages, the browser's own add-on listing, and the built-in
   * PDF viewer all do, and `activeTab` covers only the tab the user acted on.
   */
  | "not-injectable"
  | "injection-failed";

export interface ScriptingError {
  readonly kind: ScriptingErrorKind;
  readonly message: string;
}

/**
 * On-demand injection, which is what `activeTab` + `scripting` buys:
 * nothing runs on any page until the user asks for a clipping there.
 */
export interface ScriptingPort {
  inject(tabId: number): Promise<Result<void, ScriptingError>>;
}

const NO_TAB = /no tab with id|no window with id|tab was closed/i;
const NOT_INJECTABLE =
  /cannot access|missing host permission|extension manifest must request permission|cannot be scripted|not allowed|about:|chrome:\/\/|moz-extension:/i;

function classify(cause: unknown): ScriptingError {
  const message = cause instanceof Error ? cause.message : String(cause);
  if (NO_TAB.test(message)) return { kind: "no-tab", message };
  if (NOT_INJECTABLE.test(message)) return { kind: "not-injectable", message };
  return { kind: "injection-failed", message };
}

export function createScripting(): ScriptingPort {
  return {
    async inject(tabId: number): Promise<Result<void, ScriptingError>> {
      try {
        await browser.scripting.executeScript({
          target: { tabId },
          files: [CONTENT_SCRIPT_FILE],
        });
        return ok(undefined);
      } catch (cause) {
        return err(classify(cause));
      }
    },
  };
}
