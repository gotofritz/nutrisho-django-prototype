import type { Step } from "./recipe-draft";
import { err, ok, type Result } from "./result";

/**
 * The method, rewritten by the user's own model (plan 012, M13, #181):
 * short, precise and colloquial, a stage of the cooking to a step, in
 * English. Unlike an ingredient line, a rewrite cannot be checked against
 * its source word for word, so the answer is checked for its shape only;
 * Undo puts the steps back.
 */
const SHAPE = "The model's answer was not in the shape asked for.";

function stepOf(value: unknown): Step | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const { title = "", text } = value as { title?: unknown; text?: unknown };
  if (typeof title !== "string" || typeof text !== "string") return undefined;
  return { title: title.trim(), text: text.trim() };
}

export function readStepsAnswer(answer: unknown): Result<Step[], string> {
  const listed =
    typeof answer === "object" && answer !== null
      ? (answer as { steps?: unknown }).steps
      : undefined;
  if (!Array.isArray(listed)) return err(SHAPE);
  const steps = listed.map(stepOf);
  if (steps.includes(undefined)) return err(SHAPE);
  if (steps.length === 0) return err("The model answered no steps.");
  if ((steps as Step[]).some((step) => step.text === "")) {
    return err("The model answered an empty step.");
  }
  return ok(steps as Step[]);
}

/** What the model did to the method, for the sidebar to say. */
export function describeSteps(before: number, after: number): string {
  return `The model rewrote ${before} ${before === 1 ? "step" : "steps"} as ${after}.`;
}

export const STEPS_SCHEMA = {
  type: "object",
  properties: {
    steps: {
      type: "array",
      items: {
        type: "object",
        properties: { title: { type: "string" }, text: { type: "string" } },
        required: ["title", "text"],
      },
    },
  },
  required: ["steps"],
} as const;

/**
 * A rewrite, before and after: one step's text to a string, titles left out.
 */
export interface StepsExample {
  readonly before: readonly string[];
  readonly after: readonly string[];
}

/**
 * Five of the person's own rewrites (#181), one for each move: a long step
 * split, two merged, one trimmed, a technique explained. Only what the
 * originals say: where a hand-made rewrite drew on another part of the
 * recipe, that part is left out, so the model does not learn to add.
 */
export const STEPS_EXAMPLES: readonly StepsExample[] = [
  {
    before: [
      "Heat the oil in a large pot on medium heat. Add the mustard seeds and curry leaves and cook for a minute until the seeds begin to pop. Add the onion and carrots and saute for 5 minutes stirring occasionally until the onion is soft. Add the aubergine, okra and salt and cook for a further 5 minutes. Add the dal mixture, the ground coconut and spice mixture, and the 300 mls of water and bring to a simmer. Simmer partially covered for 30 minutes or until the vegetables are tender and the mixture is thickened but still slightly soupy.",
    ],
    after: [
      "Fry the mustard seeds and curry leaves in oil for a minute until the seeds begin to pop. Add the onion and carrots and sauté for 5 mins until soft",
      "Add the veg and salt and cook for a further 5 mins",
      "Add the dal mixture, the ground coconut and spice mixture, and the 300 mls of water and simmer partially covered for 30 mins",
    ],
  },
  {
    before: [
      "When ready to cook, heat a wok over high heat until just starting to smoke. Add 1 tablespoon of oil around the perimeter of the wok. Add the pork, and stir-fry until browned. Reduce the heat to medium, remove the pork from the wok and set aside. Add the remaining oil to the wok and stir-fry the mushrooms for 2 minutes. Break up the noodles gently with your hands, and add them to the wok with the mushrooms.",
    ],
    after: [
      "Stir-fry pork in a hot wok, 1 tbsp of oil, until browned",
      "Remove pork and lower heat to medium",
      "Add the rest of the oil and stir-fry mushrooms for 2 mins",
      "Add noodles to wok and mix in",
    ],
  },
  {
    before: [
      "Remove the roasting tray from the oven and add the cider, a little of the stock and give it a good stir over a low flame. This will remove any residue from the tray and begin the thickening process. Transfer everything into a large saucepan, cover with the rest of the beef or chicken stock (and some cold water if the stock doesn't cover the bones) and add the peppercorns, thyme and bay leaf.",
    ],
    after: [
      "Take out roasting pan and put over stove over a low flame",
      "Deglaze with the cider and a bit of the stock (i.e., pour the liquid, let it sizzle a few seconds, then scrape the sediments from the bottom of the pan)",
      "Transfer to a pot and add the rest of the stock, the peppercorns, thyme and bay leaf. Add water if bones are not covered",
    ],
  },
  {
    before: [
      "Meanwhile, make the tamarind water. Place the tamarind pulp in a small bowl and pour over the boiling water. Set aside for 20 minutes, then rub the pulp between your fingers until the texture of the water is thick - similar to ketchup.",
      "Pour the tamarind and water through a fine mesh strainer with a bowl underneath to catch the liquid. Press down on the tamarind fibres to extract as much flavour and liquid as possible, then discard the tamarind pulp.",
    ],
    after: [
      "Meanwhile, soak the tamarind in boiling water for 20 mins, then rub the pulp between your fingers and sieve",
    ],
  },
  {
    before: [
      "Warm a wide frying pan on medium heat and add the spices, coconut, and chilies. Stir the mixture constantly for 5 minutes until the coconut has become dry and has a toasted, golden colour. Place the mixture in a mortar and pestle and grind to a powder.",
    ],
    after: [
      "Dry roast the spices, coconut, and chilies for 5 mins, stirring constantly. Grind to a powder",
    ],
  },
];

function stepsOf(texts: readonly string[]): Step[] {
  return texts.map((text) => ({ title: "", text }));
}

/** What the model is told, before the steps; nothing about the user or the page. */
export const STEPS_INSTRUCTION = [
  "You rewrite the method of a recipe for a cook to follow at the stove.",
  'The user sends a JSON array of steps, each with a title and a text. Answer with JSON only: {"steps": [{"title": "...", "text": "..."}, ...]}.',
  "Write in English: translate anything that is not.",
  "Summarise in short, precise and colloquial language, as a friend would say it: mins for minutes, veg for vegetables, temperatures in °C only.",
  "Keep every time and temperature, and a quantity only where the step needs it, such as part of an ingredient or the water to add: the ingredient list has the rest.",
  "Drop what any cook knows, such as heating the pan first, stirring now and then or rinsing, and any padding. Where a home cook may not know a technique, explain it briefly in brackets.",
  "Keep each step focused on one stage of the cooking: split a long step into several, and merge steps that are one stage.",
  "Never add an ingredient, quantity, time or step that the steps sent do not have.",
  "Keep a title only where the steps sent have one; otherwise leave it empty.",
  "For example:",
  ...STEPS_EXAMPLES.flatMap((example) => [
    `These steps: ${JSON.stringify(stepsOf(example.before))}`,
    `become: ${JSON.stringify({ steps: stepsOf(example.after) })}`,
  ]),
].join("\n");
