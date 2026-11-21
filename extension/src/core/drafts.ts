import type { Clipping } from "./clipping";
import {
  addTo,
  isRecipeDraft,
  replace,
  startDraft,
  type RecipeDraft,
} from "./recipe-draft";
import type { Vocabulary } from "./vocabulary";

/**
 * Every draft the sidebar holds (plan 012, M7). Kept in extension storage, so
 * a draft survives the sidebar closing. A capture from another page starts a
 * new draft, and the earlier ones stay listed until they are saved or
 * discarded.
 */
export interface Drafts {
  readonly drafts: readonly RecipeDraft[];
  /** The id of the draft on show. */
  readonly current?: string;
  /** The last clipping applied, by when it was clipped, so it is applied once. */
  readonly lastClip?: string;
  /** What the server answered, by draft id, for the drafts saved. */
  readonly saved: Readonly<Record<string, SavedRecipe>>;
}

/** What a save answered: where the recipe is, and what the server noted. */
export interface SavedRecipe {
  /** The recipe's page on the user's Nutrisho, in edit mode. */
  readonly openUrl: string;
  /** The name it was saved under. */
  readonly name: string;
  /** False when the server already had it: nothing was written. */
  readonly created: boolean;
  /** The name was taken, so the server gave it another. */
  readonly renamed: boolean;
  /** Saved before, and since moved to the trash. */
  readonly inTrash: boolean;
  readonly warnings: readonly string[];
}

export const EMPTY_DRAFTS: Drafts = { drafts: [], saved: {} };

export function currentDraft(drafts: Drafts): RecipeDraft | undefined {
  return drafts.drafts.find((draft) => draft.id === drafts.current);
}

/**
 * A clipping arrived. From the page of a draft already held, that draft is
 * shown; from any other page a new draft starts, and the saved ones are
 * dropped. The text goes to the clipboard, and to the part of the draft the
 * submenu named: the title replaces the name, the rest add to what is there.
 */
export function afterClip(
  drafts: Drafts,
  clipping: Clipping,
  newId: () => string,
  vocabulary: Vocabulary,
): Drafts {
  if (drafts.lastClip === clipping.clippedAt) return drafts;

  const shown = landIn(drafts, clipping, newId);
  const { target } = clipping;
  const draft = currentDraft(shown);
  if (target === "clipboard" || draft === undefined) return shown;
  const send = target === "name" ? replace : addTo;
  return withDraft(shown, send(draft, target, clipping.text, vocabulary));
}

/** The drafts with the one the clipping belongs to on show, new if need be. */
function landIn(
  drafts: Drafts,
  clipping: Clipping,
  newId: () => string,
): Drafts {
  const unsaved = drafts.drafts.filter((draft) => !(draft.id in drafts.saved));
  const held = unsaved.find((draft) => draft.source === clipping.url);
  const shown = currentDraft(drafts);
  if (shown?.source === clipping.url) {
    return { ...drafts, lastClip: clipping.clippedAt };
  }
  if (held !== undefined) {
    return { ...drafts, current: held.id, lastClip: clipping.clippedAt };
  }

  const draft = startDraft({
    id: newId(),
    title: clipping.title,
    url: clipping.url,
    now: clipping.clippedAt,
  });
  return {
    drafts: [...unsaved, draft],
    current: draft.id,
    lastClip: clipping.clippedAt,
    saved: {},
  };
}

export function choose(drafts: Drafts, id: string): Drafts {
  return drafts.drafts.some((draft) => draft.id === id)
    ? { ...drafts, current: id }
    : drafts;
}

export function discard(drafts: Drafts, id: string): Drafts {
  const left = drafts.drafts.filter((draft) => draft.id !== id);
  const saved = Object.fromEntries(
    Object.entries(drafts.saved).filter(([key]) => key !== id),
  );
  const current =
    drafts.current === id ? left[left.length - 1]?.id : drafts.current;
  return {
    ...drafts,
    drafts: left,
    saved,
    ...(current === undefined ? { current: undefined } : { current }),
  };
}

/** The draft, changed, in its place in the list. */
export function withDraft(drafts: Drafts, changed: RecipeDraft): Drafts {
  return {
    ...drafts,
    drafts: drafts.drafts.map((draft) =>
      draft.id === changed.id ? changed : draft,
    ),
  };
}

export function markSaved(
  drafts: Drafts,
  id: string,
  saved: SavedRecipe,
): Drafts {
  return { ...drafts, saved: { ...drafts.saved, [id]: saved } };
}

/** Enough of a shape check to tell the drafts from whatever else is stored. */
export function isDrafts(value: unknown): value is Drafts {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<Record<keyof Drafts, unknown>>;
  return (
    Array.isArray(candidate.drafts) &&
    candidate.drafts.every(isRecipeDraft) &&
    typeof candidate.saved === "object" &&
    candidate.saved !== null
  );
}
