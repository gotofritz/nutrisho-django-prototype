import { mount } from "svelte";

import { clippingFrom, type Clipping } from "@/core/clipping";
import {
  EMPTY_DRAFTS,
  afterClip,
  currentDraft,
  markSaved,
  withDraft,
  type Drafts,
} from "@/core/drafts";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { createFakeDraftStore } from "@/core/ports/fakes/fake-draft-store";
import { createFakeNutrishoClient } from "@/core/ports/fakes/fake-nutrisho-client";
import { createFakeLineModel } from "@/core/ports/fakes/fake-line-model";
import { createFakeModelSettingsStore } from "@/core/ports/fakes/fake-model-settings-store";
import { createFakeSettingsStore } from "@/core/ports/fakes/fake-settings-store";
import { defaultsFor } from "@/core/model-settings";
import type { NutrishoClient, NutrishoError } from "@/core/ports/types";
import { withDetails, type RecipeDraft } from "@/core/recipe-draft";
import { err, ok } from "@/core/result";
import { DEFAULT_SETTINGS } from "@/core/settings";
import type { Vocabulary } from "@/core/vocabulary";
import ModelForm from "@/options/ModelForm.svelte";
import SettingsForm from "@/options/SettingsForm.svelte";
import Sidebar from "@/sidebar/Sidebar.svelte";
import type { LogEntry } from "@/nutrisho/fetch-log";

/** One state of the clipper, mounted into the page. */
export interface Scene {
  readonly label: string;
  readonly mount: (target: HTMLElement) => void;
}

const LISTS: Vocabulary = {
  user: "cook",
  ingredients: [
    { name: "aubergine", spellings: ["aubergines"] },
    { name: "olive oil", spellings: [] },
    { name: "rigatoni", spellings: [] },
    { name: "basil", spellings: [] },
    { name: "ricotta salata", spellings: [] },
  ],
  units: [
    { name: "g", spellings: ["grams"] },
    { name: "tbsp", spellings: ["tablespoon", "tablespoons"] },
  ],
  cuisines: ["med", "med.italy", "med.italy.sicily"],
  tags: ["dinner", "vegetarian"],
  limits: { recipe_name: 200, step_title: 128 },
};

const CLIPPING: Clipping = clippingFrom(
  {
    text: "2 aubergines, cubed\n3 tbsp olive oil\n400 g rigatoni\na handful of basil, torn\n60 g ricotta salata",
    title: "Pasta alla Norma — Example Kitchen",
    url: "https://example.test/norma",
    warnings: [],
  },
  new Date("2026-11-20T09:30:00Z"),
  "group",
);

const CLIPPED: Drafts = afterClip(EMPTY_DRAFTS, CLIPPING, () => "norma", LISTS);

/** The clipped draft, filled in as far as a user would before saving. */
function filled(): Drafts {
  const draft = currentDraft(CLIPPED)!;
  const done: RecipeDraft = {
    ...withDetails(draft, {
      name: "Pasta alla Norma",
      blurb: "Fried aubergine, tomato and salted ricotta, as in Catania.",
      servings: "4",
      cuisine: "med.italy.sicily",
    }),
    tags: ["dinner", "summer"],
    steps: [
      { title: "", text: "Fry the aubergine in the oil until golden." },
      { title: "To serve", text: "Toss with the pasta, basil and ricotta." },
    ],
  };
  return withDraft(CLIPPED, done);
}

function client(lists: "loaded" | NutrishoError = "loaded"): NutrishoClient {
  const fake = createFakeNutrishoClient();
  fake.answerVocabulary(lists === "loaded" ? ok(LISTS) : err(lists));
  return fake;
}

/** What a sidebar that has loaded the lists and saved once has logged. */
const LOG: readonly LogEntry[] = [
  "→ GET http://127.0.0.1:8987/recipes/api/vocabulary/",
  "← 200 OK · 14.2 kB · 38 ms",
  "→ POST http://127.0.0.1:8987/recipes/api/recipes/ · 1.9 kB",
  "← 201 Created · 412 B · 91 ms",
].map((text, index) => ({
  at: new Date(Date.UTC(2026, 10, 22, 4, 26, index)),
  text,
}));

function sidebar(
  options: {
    readonly clipping?: Clipping;
    readonly drafts?: Drafts;
    readonly client?: NutrishoClient;
  } = {},
): Scene["mount"] {
  return (target) =>
    void mount(Sidebar, {
      target,
      props: {
        clippings: createFakeClippingStore(options.clipping),
        drafts: createFakeDraftStore(options.drafts),
        newId: () => crypto.randomUUID(),
        subscribe: () => () => {},
        client: options.client ?? client(),
        openSettings: () => {},
        isNewSession: async () => false,
        settings: createFakeSettingsStore(),
        requestHostPermission: async () => true,
        log: LOG,
        model: createFakeLineModel(),
        modelSettings: createFakeModelSettingsStore(defaultsFor("mlx")),
      },
    });
}

export const SCENES: Readonly<Record<string, Scene>> = {
  empty: { label: "Nothing clipped", mount: sidebar() },
  expired: {
    label: "Key expired",
    mount: sidebar({
      client: client({
        kind: "key-expired",
        status: 401,
        message: "This API token has expired: make a new one.",
      }),
    }),
  },
  unreachable: {
    label: "Server down",
    mount: sidebar({
      client: client({ kind: "unreachable", message: "NetworkError" }),
    }),
  },
  clipped: {
    label: "Just clipped",
    mount: sidebar({ clipping: CLIPPING, drafts: CLIPPED }),
  },
  filled: {
    label: "Filled in",
    mount: sidebar({ clipping: CLIPPING, drafts: filled() }),
  },
  saved: {
    label: "Saved",
    mount: sidebar({
      clipping: CLIPPING,
      drafts: markSaved(filled(), "norma", {
        openUrl: "http://localhost:8987/recipes/norma/?edit=1",
        name: "Pasta alla Norma",
        created: true,
        renamed: false,
        inTrash: false,
        warnings: ["summer is now one of your own tags."],
      }),
    }),
  },
  settings: {
    label: "Settings",
    mount: (target) => {
      mount(SettingsForm, {
        target,
        props: {
          settings: createFakeSettingsStore({
            ...DEFAULT_SETTINGS,
            apiKey: "",
          }),
          requestHostPermission: async () => true,
        },
      });
      mount(ModelForm, {
        target,
        props: {
          store: createFakeModelSettingsStore(defaultsFor("mlx")),
          requestHostPermission: async () => true,
        },
      });
    },
  },
};

export const DEFAULT_SCENE = "filled";
