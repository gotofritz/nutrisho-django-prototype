/**
 * What one capture off a page amounts to, before any of it becomes a recipe
 * (plan 012, M6). A plain value with no DOM in it: `src/content/extract.dom.ts`
 * fills it in from a live page, and nothing importing this module needs a
 * browser.
 *
 * Only what the user selected, and the page's title and address, are read
 * (D15): a recipe needs nothing else from the page.
 */

/** Select-all on a long article is megabytes; the cap bites first. */
export const SELECTION_CAP = 20_000;

/**
 * What could not be captured, or was captured only in part. A clipping
 * silently missing text is worse than a message saying so, and each kind
 * names a different thing for the user to do about it.
 */
export type CaptureWarningKind =
  /** The selection was longer than `SELECTION_CAP`. */
  | "selection-truncated"
  /** `getSelection()` does not reach into a shadow root. */
  | "shadow-dom"
  /** A cross-origin frame is a separate context; this one cannot read it. */
  | "cross-origin-frame"
  /** No content script ran — a privileged page, or the built-in PDF viewer. */
  | "no-content-script";

export interface CaptureWarning {
  readonly kind: CaptureWarningKind;
  readonly message: string;
}

export function warn(
  kind: CaptureWarningKind,
  message: string,
): CaptureWarning {
  return { kind, message };
}

/** One capture: the selection, and the page it came from. */
export interface PageCapture {
  /** The selection as plain text, a line per block, capped. */
  readonly text: string;
  readonly title: string;
  readonly url: string;
  readonly warnings: readonly CaptureWarning[];
}

export interface CappedText {
  readonly text: string;
  readonly truncated: boolean;
}

/** Cut at the cap and say whether it cut. The caller decides what to warn. */
export function capText(value: string, cap: number): CappedText {
  return value.length <= cap
    ? { text: value, truncated: false }
    : { text: value.slice(0, cap), truncated: true };
}
