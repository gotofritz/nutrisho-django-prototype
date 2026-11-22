import { beforeEach, describe, expect, it } from "vitest";

import { SELECTION_CAP } from "@/core/capture";

import { extractCapture } from "./extract.dom";

function select(
  start: Node,
  startOffset: number,
  end: Node,
  endOffset: number,
) {
  const range = document.createRange();
  range.setStart(start, startOffset);
  range.setEnd(end, endOffset);

  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

function selectContentsOf(node: Node) {
  const range = document.createRange();
  range.selectNodeContents(node);

  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

function textOf(selector: string): Text {
  const node = document.querySelector(selector)?.firstChild;
  if (!node) throw new Error(`no text node in ${selector}`);
  return node as Text;
}

function extract() {
  return extractCapture({ document, window });
}

function kinds(warnings: readonly { kind: string }[]) {
  return warnings.map((warning) => warning.kind);
}

beforeEach(() => {
  document.body.innerHTML = "";
  window.getSelection()?.removeAllRanges();
});

describe("extractCapture", () => {
  it("takes the selected text", () => {
    document.body.innerHTML = `
      <p id="one">Toast the pine nuts. Then blend them with the basil.</p>
      <p id="two">Season.</p>`;
    const paragraph = textOf("#one");
    select(paragraph, 0, paragraph, 19);

    expect(extract().text).toBe("Toast the pine nuts");
  });

  // Plan 012, M6: a recipe's ingredients are list items and its steps are
  // paragraphs, and each one has to arrive as a line of its own.
  it("gives each list item a line of its own", () => {
    document.body.innerHTML = `
      <ul id="target"><li>2 aubergines</li><li>1 tbsp <b>olive</b> oil</li><li>basil</li></ul>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe("2 aubergines\n1 tbsp olive oil\nbasil");
  });

  // Some sites wrap part of an ingredient, `(about 2 tsp)`, in an element of
  // its own, or break it with a <br>: inside a list item it is one line.
  it("keeps what is inside one list item on one line", () => {
    document.body.innerHTML = `
      <ul id="target"><li>4g allspice berries<div>(about 2 tsp)</div></li><li>1 medium shallot,<br />peeled and sliced</li></ul>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe(
      "4g allspice berries (about 2 tsp)\n1 medium shallot, peeled and sliced",
    );
  });

  // A line break in the page's source is a space on screen; only the markup
  // breaks a line. The markup a user clipped, as the page gave it.
  it("reads a line break in the page's source as a space", () => {
    document.body.innerHTML = `<p id="target">For the pickled raisins
 <br>
 <strong>500g apple cider vinegar
  <br>8g black peppercorns </strong>(about 1 tbsp)<strong>
  <br>4g allspice berries 
 </strong>(about 2 tsp)<strong>
  <br>2 bay leaves
  <br>1 medium shallot,
 </strong> peeled and sliced
 <br>
 <strong>1 </strong><strong>fresh jalapeño chilli</strong>, left whole</p>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text.split("\n")).toEqual([
      "For the pickled raisins",
      "500g apple cider vinegar",
      "8g black peppercorns (about 1 tbsp)",
      "4g allspice berries (about 2 tsp)",
      "2 bay leaves",
      "1 medium shallot, peeled and sliced",
      "1 fresh jalapeño chilli, left whole",
    ]);
  });

  it("keeps the line breaks of preformatted text", () => {
    document.body.innerHTML = `<pre id="target">2 lemons
1 lime</pre>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe("2 lemons\n1 lime");
  });

  it("gives each paragraph a line of its own, and a <br> breaks one", () => {
    document.body.innerHTML = `
      <div id="target"><p>Heat the oven.</p><p>Slice the <i>aubergines</i>.<br />Salt them.</p></div>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe(
      "Heat the oven.\nSlice the aubergines.\nSalt them.",
    );
  });

  it("leaves out what the page does not show", () => {
    document.body.innerHTML = `
      <div id="target"><p>Heat the oven.</p><script>track()</script><style>p{}</style></div>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe("Heat the oven.");
  });

  it("truncates a selection over the cap and flags the truncation", () => {
    const long = "z".repeat(SELECTION_CAP + 500);
    document.body.innerHTML = `<p id="target">${long}</p>`;
    selectContentsOf(document.querySelector("#target")!);

    const capture = extract();

    expect(capture.text).toHaveLength(SELECTION_CAP);
    expect(kinds(capture.warnings)).toContain("selection-truncated");
  });

  it("collapses runs of whitespace without collapsing the line breaks", () => {
    document.body.innerHTML = `
      <div id="target"><p>Spaced      out</p><p>and     wrapped</p></div>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).toBe("Spaced out\nand wrapped");
  });

  it("reports the shadow-DOM blind spot rather than returning empty text", () => {
    document.body.innerHTML = `<div id="host"></div>`;
    const host = document.querySelector("#host")!;
    host.attachShadow({ mode: "open" }).innerHTML = `<p>Heat the oven.</p>`;
    const range = document.createRange();
    range.selectNode(host);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);

    const capture = extract();

    expect(capture.text).toBe("");
    expect(kinds(capture.warnings)).toContain("shadow-dom");
  });

  it("reports the cross-origin frame blind spot", () => {
    document.body.innerHTML = `<iframe id="frame"></iframe><p id="empty"></p>`;
    const frame = document.querySelector("#frame")!;
    Object.defineProperty(frame, "contentDocument", {
      get() {
        throw new Error("blocked a frame with origin from accessing a frame");
      },
    });
    selectContentsOf(document.querySelector("#empty")!);

    expect(kinds(extract().warnings)).toContain("cross-origin-frame");
  });

  it("records the page's own title and url", () => {
    document.title = "Melanzane — Example";
    document.body.innerHTML = `<p id="target">Heat the oven.</p>`;
    selectContentsOf(document.querySelector("#target")!);

    const capture = extract();

    expect(capture.title).toBe("Melanzane — Example");
    expect(capture.url).toBe(window.location.href);
  });

  // Plan 012, D15: only what the user selected is read off the page.
  it("reads nothing but the selection, its page's title and its address", () => {
    document.body.innerHTML = `<p id="target">Heat the oven.</p><p>Not this.</p>`;
    selectContentsOf(document.querySelector("#target")!);

    expect(extract().text).not.toContain("Not this");
    expect(Object.keys(extract()).sort()).toEqual([
      "text",
      "title",
      "url",
      "warnings",
    ]);
  });

  it("returns an empty capture when nothing is selected", () => {
    document.body.innerHTML = `<p>Heat the oven.</p>`;

    const capture = extract();

    expect(capture.text).toBe("");
    expect(capture.warnings).toEqual([]);
  });
});
