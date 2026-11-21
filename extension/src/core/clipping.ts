import type { CaptureWarning, PageCapture } from "./capture";
import type { DraftTarget } from "./recipe-draft";

/** Where the text goes: a part of the draft as well as the clipboard, or the clipboard only. */
export type ClipTarget = DraftTarget | "clipboard";

const TARGETS: readonly ClipTarget[] = [
  "name",
  "blurb",
  "group",
  "steps",
  "clipboard",
];

/**
 * What a capture leaves for the sidebar (plan 012, M6): the selected text and
 * the page it came from. The text goes to the sidebar's clipboard, and a
 * clipping from a page with no draft starts one (M7).
 *
 * Stored rather than sent: the background is unloaded when idle and the
 * sidebar may not be open yet, so the capture writes it to extension storage
 * and the sidebar reads it from there.
 */
export interface Clipping {
  /** A line per list item, paragraph or `<br>` on the page. */
  readonly text: string;
  readonly title: string;
  readonly url: string;
  /** ISO 8601, so it survives storage unchanged. */
  readonly clippedAt: string;
  /** What could not be read, or was read only in part. */
  readonly warnings: readonly CaptureWarning[];
  /** Chosen in the right-click submenu; the shortcut and the button send to the clipboard. */
  readonly target: ClipTarget;
}

export function clippingFrom(
  capture: PageCapture,
  now: Date,
  target: ClipTarget = "clipboard",
): Clipping {
  return {
    text: capture.text,
    title: capture.title,
    url: capture.url,
    clippedAt: now.toISOString(),
    warnings: capture.warnings,
    target,
  };
}

/** Enough of a shape check to tell a clipping from whatever else is stored. */
export function isClipping(value: unknown): value is Clipping {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<Record<keyof Clipping, unknown>>;

  return (
    typeof candidate.text === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.url === "string" &&
    typeof candidate.clippedAt === "string" &&
    Array.isArray(candidate.warnings) &&
    TARGETS.includes(candidate.target as ClipTarget)
  );
}
