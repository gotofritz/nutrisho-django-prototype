import type { CaptureWarning, PageCapture } from "@/core/capture";
import { SELECTION_CAP, capText, warn } from "@/core/capture";

/**
 * Extraction off a live page, copied from anklipper.
 *
 * `info.selectionText` from the context-menu event is flattened to one line by
 * the browser, so the menu click is the trigger and this is what actually
 * reads the page: a line per list item, paragraph or `<br>`, which is what
 * makes a recipe's ingredients and steps separable. The `.dom` in the filename
 * is the repo's marker for a module that needs a document — its tests run in
 * jsdom.
 */
export interface ExtractDeps {
  readonly document: Document;
  readonly window: Window;
}

/** Elements that start a new line when a page is read aloud. */
const BLOCK_TAGS = new Set([
  "ADDRESS",
  "ARTICLE",
  "ASIDE",
  "BLOCKQUOTE",
  "DD",
  "DIV",
  "DL",
  "DT",
  "FIELDSET",
  "FIGCAPTION",
  "FIGURE",
  "FOOTER",
  "FORM",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HEADER",
  "HR",
  "LI",
  "MAIN",
  "NAV",
  "OL",
  "P",
  "PRE",
  "SECTION",
  "TABLE",
  "TD",
  "TH",
  "TR",
  "UL",
]);

function isBlock(element: Element): boolean {
  return BLOCK_TAGS.has(element.tagName);
}

function asElement(node: Node | null): Element | null {
  if (!node) return null;
  return node.nodeType === 1 ? (node as Element) : node.parentElement;
}

/** Collapse spaces and tabs, keep the line breaks the blocks earned. */
function tidy(value: string): string {
  return value
    .replace(/[^\S\n]+/g, " ")
    .replace(/ *\n+ */g, "\n")
    .trim();
}

/**
 * Flatten a fragment to text: the markup decides only where lines break.
 * Inside a list item nothing breaks, since an item is one ingredient or step
 * even when the page wraps `(about 2 tsp)` in an element of its own.
 */
interface Context {
  /** Inside a list item, where nothing breaks a line. */
  readonly inItem: boolean;
  /** Inside `<pre>`, where the source's line breaks show. */
  readonly pre: boolean;
}

function flatten(node: Node, into: string[], context: Context): void {
  const { inItem, pre } = context;
  if (node.nodeType === 3) {
    // A line break in the source shows as a space, except in <pre>.
    const data = (node as Text).data;
    into.push(pre ? data : data.replace(/\s+/g, " "));
    return;
  }
  if (node.nodeType !== 1 && node.nodeType !== 11) return;

  const element = node.nodeType === 1 ? (node as Element) : undefined;
  if (element?.tagName === "BR") {
    into.push(inItem ? " " : "\n");
    return;
  }
  // Anything the page does not render is not part of the selection's text.
  if (
    element &&
    (element.tagName === "SCRIPT" || element.tagName === "STYLE")
  ) {
    return;
  }

  const breaks = element !== undefined && isBlock(element);
  const edge = breaks && !inItem ? "\n" : breaks ? " " : "";
  const inner = {
    inItem: inItem || element?.tagName === "LI",
    pre: pre || element?.tagName === "PRE",
  };
  into.push(edge);
  for (const child of Array.from(node.childNodes)) flatten(child, into, inner);
  into.push(edge);
}

/** What the selection sits inside, which its clone leaves out. */
function contextOf(range: Range): Context {
  const around = asElement(range.commonAncestorContainer);
  return {
    inItem: around?.closest("li") != null,
    pre: around?.closest("pre") != null,
  };
}

function fragmentToText(range: Range): string {
  const parts: string[] = [];
  flatten(range.cloneContents(), parts, contextOf(range));
  return tidy(parts.join(""));
}

/** `getSelection()` does not reach into a shadow root, open or closed. */
function touchesShadowRoot(range: Range): boolean {
  const root = asElement(range.commonAncestorContainer);
  if (!root) return false;
  if (root.shadowRoot) return true;

  return Array.from(root.querySelectorAll("*")).some(
    (element) => element.shadowRoot !== null && range.intersectsNode(element),
  );
}

/** A cross-origin frame is a separate context; reading it throws. */
function hasUnreadableFrame(doc: Document): boolean {
  return Array.from(doc.querySelectorAll("iframe, frame")).some((frame) => {
    try {
      return (frame as HTMLIFrameElement).contentDocument === null;
    } catch {
      return true;
    }
  });
}

function firstRange(win: Window): Range | undefined {
  const selection = win.getSelection();
  if (!selection || selection.rangeCount === 0) return undefined;
  return selection.getRangeAt(0);
}

/**
 * Read the current selection.
 *
 * Never throws and never returns nothing: a blind spot becomes a warning
 * naming what could not be captured, and the caller still gets a capture.
 */
export function extractCapture(deps: ExtractDeps): PageCapture {
  const { document: doc, window: win } = deps;
  const warnings: CaptureWarning[] = [];
  const page = { title: doc.title, url: win.location.href };

  const range = firstRange(win);
  if (!range) return { text: "", ...page, warnings };

  const selection = capText(fragmentToText(range), SELECTION_CAP);
  if (selection.truncated) {
    warnings.push(
      warn(
        "selection-truncated",
        `only the first ${SELECTION_CAP} characters of the selection were captured`,
      ),
    );
  }

  if (selection.text === "") {
    if (touchesShadowRoot(range)) {
      warnings.push(
        warn(
          "shadow-dom",
          "the selection is inside a shadow root, which the page script cannot read",
        ),
      );
    } else if (hasUnreadableFrame(doc)) {
      warnings.push(
        warn(
          "cross-origin-frame",
          "the selection is inside a frame from another site, which the page script cannot read",
        ),
      );
    }
  }

  return { text: selection.text, ...page, warnings };
}
