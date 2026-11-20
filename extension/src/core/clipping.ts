import type { CaptureWarning, PageCapture } from "./capture";

/**
 * What a capture leaves for the sidebar (plan 012, M6): the selected text and
 * the page it came from. Nothing is a recipe yet; M7 turns a clipping into a
 * draft.
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
}

export function clippingFrom(capture: PageCapture, now: Date): Clipping {
  return {
    text: capture.text,
    title: capture.title,
    url: capture.url,
    clippedAt: now.toISOString(),
    warnings: capture.warnings,
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
    Array.isArray(candidate.warnings)
  );
}
