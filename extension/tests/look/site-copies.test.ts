import { readFileSync, readdirSync } from "node:fs";
import { relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The clipper looks like the site (plan 012, M12, D19): its tokens, its two
 * text faces and its lineout plate are copies of the server's. A change on
 * either side fails here until the other follows; the extension workflow runs
 * on a change to these server files too.
 */
const EXTENSION = resolve(import.meta.dirname, "../..");
const STATIC = resolve(EXTENSION, "../server/src/recipes/static");
const SITE_CSS = readFileSync(resolve(STATIC, "css/style.css"), "utf8");
const TOKENS_CSS = readFileSync(
  resolve(EXTENSION, "src/styles/tokens.css"),
  "utf8",
);

/** The faces the clipper uses; the sheet's own (Lobster, Inconsolata) stay on the site. */
const FACES = ["Libre Caslon Text", "IM Fell English SC"];
/** The recipe sheet's own tokens, which the clipper has no sheet for. */
const SHEET_TOKENS = ["--hbar", "--color-light-light", "--color-dark-main"];

function rootTokens(css: string): Map<string, string> {
  const root = /:root\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
  return new Map(
    [...root.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [
      name!,
      value!.trim(),
    ]),
  );
}

function fontFaces(css: string): string[] {
  return [...css.matchAll(/@font-face\s*\{[^}]*\}/g)]
    .map(([block]) => block.replace(/\s+/g, " "))
    .filter((block) => FACES.some((face) => block.includes(`"${face}"`)));
}

function filesUnder(dir: string): string[] {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(dir, resolve(entry.parentPath, entry.name)))
    .sort();
}

describe("the site's look, copied", () => {
  it("has every one of the site's tokens, with the same value", () => {
    const site = rootTokens(SITE_CSS);
    for (const token of SHEET_TOKENS) site.delete(token);

    expect(site.size).toBeGreaterThan(0);
    expect(rootTokens(TOKENS_CSS)).toEqual(site);
  });

  it("declares the two text faces as the site does, from its own fonts", () => {
    const site = fontFaces(SITE_CSS).map((block) =>
      block.replaceAll('url("../fonts/', 'url("/fonts/'),
    );

    expect(site).toHaveLength(7);
    expect(fontFaces(TOKENS_CSS)).toEqual(site);
  });

  it("carries the same font files, byte for byte, and no others", () => {
    const fonts = resolve(EXTENSION, "public/fonts");
    const copied = filesUnder(fonts);
    const wanted = FACES.map((face) =>
      face.toLowerCase().replaceAll(" ", "-"),
    ).flatMap((dir) =>
      filesUnder(resolve(STATIC, "fonts", dir)).map((file) => `${dir}/${file}`),
    );

    expect(copied).toEqual(wanted.sort());
    for (const file of copied) {
      expect(
        readFileSync(resolve(fonts, file)).equals(
          readFileSync(resolve(STATIC, "fonts", file)),
        ),
        file,
      ).toBe(true);
    }
  });

  it("carries the lineout plate, byte for byte", () => {
    const plate = "img/plate-lineout.webp";

    expect(
      readFileSync(resolve(EXTENSION, "public", plate)).equals(
        readFileSync(resolve(STATIC, plate)),
      ),
    ).toBe(true);
  });
});
