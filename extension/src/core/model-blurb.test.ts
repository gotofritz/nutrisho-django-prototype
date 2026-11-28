import { describe, expect, it } from "vitest";

import {
  BLURB_EXAMPLE,
  BLURB_INSTRUCTION,
  BLURB_SCHEMA,
  blurbInput,
  describeBlurb,
  readBlurbAnswer,
} from "./model-blurb";

// #205: the model compacts the blurb, and translates it to English, as it
// does the steps.
describe("readBlurbAnswer", () => {
  it("takes the blurb it answers, tidied, and the language it was in", () => {
    expect(
      readBlurbAnswer({
        language: " Italian ",
        blurb: "  A summer salad of bread and peaches. \n",
      }),
    ).toEqual({
      ok: true,
      value: {
        language: "Italian",
        blurb: "A summer salad of bread and peaches.",
      },
    });
  });

  it("takes a blurb with no language, as an older model may answer", () => {
    expect(readBlurbAnswer({ blurb: "A salad." })).toEqual({
      ok: true,
      value: { language: "", blurb: "A salad." },
    });
  });

  it.each([
    ["not an object"],
    [null],
    [{ blurb: 3 }],
    [{ text: "A salad" }],
    [{ blurb: "A salad", language: 3 }],
  ])("refuses an answer of the wrong shape: %j", (answer) => {
    expect(readBlurbAnswer(answer)).toEqual({
      ok: false,
      error: "The model's answer was not in the shape asked for.",
    });
  });

  it("refuses an empty blurb", () => {
    expect(readBlurbAnswer({ blurb: "  " })).toEqual({
      ok: false,
      error: "The model answered an empty blurb.",
    });
  });
});

describe("blurbInput", () => {
  it("sends the blurb and nothing else", () => {
    expect(blurbInput("Una panzanella estiva.")).toEqual({
      blurb: "Una panzanella estiva.",
    });
  });
});

describe("describeBlurb", () => {
  it("says what the model did, by the name of the model that answered", () => {
    expect(describeBlurb()).toBe("The model rewrote the blurb.");
    expect(describeBlurb("Haiku")).toBe("Haiku rewrote the blurb.");
  });

  it("says what language it translated from, when it was not English", () => {
    expect(describeBlurb("Haiku", "Italian")).toBe(
      "Haiku rewrote the blurb, from Italian.",
    );
    expect(describeBlurb("Haiku", "english")).toBe("Haiku rewrote the blurb.");
    expect(describeBlurb("Haiku", "")).toBe("Haiku rewrote the blurb.");
  });
});

// Asked for again in #207: no model translated with the first prompt, which
// said "English" once, in the middle. The ingredient prompt, which does
// translate, makes the model say what it did and shows it an Italian line.
describe("BLURB_INSTRUCTION", () => {
  it("opens by asking for English, whatever the blurb's language", () => {
    const [first, second] = BLURB_INSTRUCTION.split("\n");
    expect(`${first} ${second}`).toMatch(/always in English/);
    expect(BLURB_INSTRUCTION).toMatch(/translate it/);
  });

  it("asks it to name the language the blurb was written in", () => {
    expect(BLURB_INSTRUCTION).toMatch(/"language"/);
  });

  it("asks for a compact blurb, and nothing added", () => {
    expect(BLURB_INSTRUCTION).toMatch(/short/);
    expect(BLURB_INSTRUCTION).toMatch(/Never add/);
  });

  it("shows an Italian blurb, and its English answer", () => {
    expect(BLURB_INSTRUCTION).toContain(JSON.stringify(BLURB_EXAMPLE.before));
    expect(BLURB_INSTRUCTION).toContain(JSON.stringify(BLURB_EXAMPLE.after));
    expect(BLURB_EXAMPLE.after.language).toBe("Italian");
  });
});

describe("BLURB_SCHEMA", () => {
  it("asks for the language first, then the blurb in English", () => {
    expect(BLURB_SCHEMA.required).toEqual(["language", "blurb"]);
    expect(Object.keys(BLURB_SCHEMA.properties)).toEqual(["language", "blurb"]);
    expect(BLURB_SCHEMA.properties.blurb.description).toMatch(/English/);
  });
});
