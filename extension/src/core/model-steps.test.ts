import { describe, expect, it } from "vitest";

import {
  STEPS_EXAMPLES,
  STEPS_INSTRUCTION,
  STEPS_SCHEMA,
  describeSteps,
  readStepsAnswer,
} from "./model-steps";

// #181: the model rewrites the method short, precise and colloquial, a
// stage of the cooking to a step, as the person has been doing by hand.
describe("readStepsAnswer", () => {
  it("takes the steps it answers, tidied", () => {
    expect(
      readStepsAnswer({
        steps: [
          { title: "", text: " Fry the seeds until they pop. " },
          { text: "Add the veg and salt." },
        ],
      }),
    ).toEqual({
      ok: true,
      value: [
        { title: "", text: "Fry the seeds until they pop." },
        { title: "", text: "Add the veg and salt." },
      ],
    });
  });

  it.each([
    ["not an object"],
    [{ steps: "Fry" }],
    [{ steps: [{ title: 3, text: "Fry" }] }],
    [{ steps: [{ title: "" }] }],
    [{ steps: [null] }],
  ])("refuses an answer of the wrong shape: %j", (answer) => {
    expect(readStepsAnswer(answer)).toEqual({
      ok: false,
      error: "The model's answer was not in the shape asked for.",
    });
  });

  it("refuses an answer with no steps, or an empty one", () => {
    expect(readStepsAnswer({ steps: [] })).toEqual({
      ok: false,
      error: "The model answered no steps.",
    });
    expect(readStepsAnswer({ steps: [{ title: "", text: "  " }] })).toEqual({
      ok: false,
      error: "The model answered an empty step.",
    });
  });
});

describe("describeSteps", () => {
  it.each([
    [1, 3, "The model rewrote 1 step as 3."],
    [4, 4, "The model rewrote 4 steps as 4."],
    [3, 1, "The model rewrote 3 steps as 1."],
  ])("says %i steps became %i", (before, after, said) => {
    expect(describeSteps(before, after)).toBe(said);
  });

  // #183: the set-up that answered, by its name.
  it("names the model that answered", () => {
    expect(describeSteps(2, 1, "Haiku")).toBe("Haiku rewrote 2 steps as 1.");
  });
});

describe("STEPS_INSTRUCTION", () => {
  it("asks for short, colloquial steps in English, a stage to a step", () => {
    expect(STEPS_INSTRUCTION).toMatch(/short, precise and colloquial/);
    expect(STEPS_INSTRUCTION).toMatch(/English/);
    expect(STEPS_INSTRUCTION).toMatch(/split a long step/);
  });

  it("asks it to add nothing the steps do not say", () => {
    expect(STEPS_INSTRUCTION).toMatch(
      /Never add an ingredient, quantity, time or step/,
    );
  });

  it("shows every one of the person's own examples, before and after", () => {
    for (const example of STEPS_EXAMPLES) {
      for (const text of [...example.before, ...example.after]) {
        expect(STEPS_INSTRUCTION).toContain(JSON.stringify(text));
      }
    }
  });
});

// The person's own rewrites, done by hand before the clipper could.
describe("STEPS_EXAMPLES", () => {
  it("holds the person's examples, the dal among them", () => {
    expect(STEPS_EXAMPLES).toHaveLength(5);
    expect(STEPS_EXAMPLES.flatMap((example) => example.after)).toContain(
      "Add the veg and salt and cook for a further 5 mins",
    );
  });

  it("shows a long step split, and two steps merged", () => {
    const counts = STEPS_EXAMPLES.map((example) => [
      example.before.length,
      example.after.length,
    ]);

    expect(counts).toContainEqual([1, 4]);
    expect(counts).toContainEqual([2, 1]);
  });

  it("keeps each text tidy", () => {
    for (const example of STEPS_EXAMPLES) {
      for (const text of [...example.before, ...example.after]) {
        expect(text).toBe(text.trim());
        expect(text).not.toBe("");
      }
    }
  });
});

describe("STEPS_SCHEMA", () => {
  it("asks for a title and a text for each step", () => {
    expect(STEPS_SCHEMA.properties.steps.items.required).toEqual([
      "title",
      "text",
    ]);
  });
});
