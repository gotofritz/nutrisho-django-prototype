/**
 * A Svelte action: a textarea as tall as its text, so a step clipped from a
 * page shows whole. Its argument is the text, so a change made from outside
 * (a clip) refits it as well as typing does.
 */
export function fitText(
  area: HTMLTextAreaElement,
  text: string,
): { update: (text: string) => void; destroy: () => void } {
  function fit(): void {
    // Shrink first, or the box would only ever grow.
    area.style.height = "auto";
    // The text's height, plus the box's borders (the box is border-box).
    const borders = area.offsetHeight - area.clientHeight;
    area.style.height = `${area.scrollHeight + Math.max(borders, 0)}px`;
  }

  let shown = text;
  fit();
  area.addEventListener("input", fit);
  return {
    update: (next) => {
      if (next === shown) return;
      shown = next;
      fit();
    },
    destroy: () => area.removeEventListener("input", fit),
  };
}
