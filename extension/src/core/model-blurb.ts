import { err, ok, type Result } from "./result";

/**
 * The blurb, rewritten by the user's own model (#205): compact, and in
 * English, as the steps are (#181). Like a step, a rewrite cannot be checked
 * against its source word for word, so the answer is checked for its shape
 * only; Undo puts the blurb back.
 *
 * The first prompt said "English" once, mid-list, and no model translated
 * (#207). As the ingredient prompt does, this one opens with the language,
 * has the model name the language it read before it writes, which makes it
 * decide, and shows it an Italian blurb and its English answer.
 */
const SHAPE = "The model's answer was not in the shape asked for.";

export interface BlurbAnswer {
  /** The language the model says the blurb was in; "" if it did not say. */
  readonly language: string;
  readonly blurb: string;
}

export function readBlurbAnswer(answer: unknown): Result<BlurbAnswer, string> {
  if (typeof answer !== "object" || answer === null) return err(SHAPE);
  const { blurb, language = "" } = answer as {
    blurb?: unknown;
    language?: unknown;
  };
  if (typeof blurb !== "string" || typeof language !== "string") {
    return err(SHAPE);
  }
  if (blurb.trim() === "") return err("The model answered an empty blurb.");
  return ok({ language: language.trim(), blurb: blurb.trim() });
}

/** What the model is sent: the blurb, and nothing about the page. */
export function blurbInput(blurb: string): { readonly blurb: string } {
  return { blurb };
}

/** What the model did to the blurb, for the sidebar to say. */
export function describeBlurb(who = "The model", language = ""): string {
  const from =
    language === "" || language.toLowerCase() === "english"
      ? ""
      : `, from ${language}`;
  return `${who} rewrote the blurb${from}.`;
}

export const BLURB_SCHEMA = {
  type: "object",
  properties: {
    language: {
      type: "string",
      description: "The language the blurb sent was written in.",
    },
    blurb: {
      type: "string",
      description: "The blurb, rewritten short, in English.",
    },
  },
  required: ["language", "blurb"],
} as const;

/** An Italian blurb, and the answer the model should give for it. */
export const BLURB_EXAMPLE = {
  before: {
    blurb:
      "La panzanella è un piatto povero della tradizione toscana, nato per non sprecare il pane raffermo. In questa versione estiva, che ho imparato da mia nonna, il pane si sposa con pesche tabacchiere e pomodorini: provatela, non ve ne pentirete! Iscrivetevi alla newsletter per altre ricette.",
  },
  after: {
    language: "Italian",
    blurb:
      "A Tuscan bread salad, made to use up stale bread. This summer version adds flat peaches to the tomatoes.",
  },
} as const;

/** What the model is told, before the blurb; nothing about the user or the page. */
export const BLURB_INSTRUCTION = [
  "You rewrite the blurb of a recipe, the few lines under its name that say what the dish is, always in English.",
  "Whatever language the blurb is written in, your blurb is in English: if it is not English, translate it.",
  'The user sends JSON: {"blurb": "..."}. Answer with JSON only: {"language": "...", "blurb": "..."}, where language names the language the blurb sent was written in, and blurb is your English one.',
  "Make it short: two or three sentences at most, in plain, colloquial language. Keep what the dish is, where it comes from and what makes it worth making; drop the story around it, praise, advertising and anything about the website or its author.",
  "Never add a fact, ingredient or claim that the blurb sent does not have.",
  "Write plain text, with a blank line between paragraphs, if there is more than one.",
  `For example, this blurb: ${JSON.stringify(BLURB_EXAMPLE.before)}`,
  `becomes: ${JSON.stringify(BLURB_EXAMPLE.after)}`,
].join("\n");
