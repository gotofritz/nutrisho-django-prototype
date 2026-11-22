import { browser } from "wxt/browser";

import { err, ok, type Result } from "@/core/result";

/**
 * The extension's own options page.
 *
 * `runtime.openOptionsPage()` on both browsers — it needs no permission, and
 * WXT generates the page's manifest entry from the `options` entrypoint. It is
 * wrapped for the same reason everything else here is: the sidebar must not
 * reach `browser.*`, and a click handler must not have an exception thrown
 * into it.
 */
export type OptionsErrorKind = "unsupported" | "open-failed";

export interface OptionsError {
  readonly kind: OptionsErrorKind;
  readonly message: string;
}

export interface OptionsPort {
  open(): Promise<Result<void, OptionsError>>;
}

export interface OptionsBackings {
  openOptionsPage?(): Promise<void>;
}

export function createOptionsPage(
  backings: OptionsBackings = browser.runtime,
): OptionsPort {
  return {
    async open(): Promise<Result<void, OptionsError>> {
      const open = backings.openOptionsPage;
      if (open === undefined) {
        return err({
          kind: "unsupported",
          message: "this browser has no options page to open",
        });
      }

      try {
        await open.call(backings);
        return ok(undefined);
      } catch (cause) {
        return err({
          kind: "open-failed",
          message: cause instanceof Error ? cause.message : String(cause),
        });
      }
    },
  };
}
