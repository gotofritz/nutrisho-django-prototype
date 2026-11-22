import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { tick } from "svelte";
import { describe, expect, it, vi } from "vitest";

import { clippingFrom, type Clipping } from "@/core/clipping";
import {
  EMPTY_DRAFTS,
  afterClip,
  currentDraft,
  withDraft,
  type Drafts,
} from "@/core/drafts";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { createFakeDraftStore } from "@/core/ports/fakes/fake-draft-store";
import { createFakeNutrishoClient } from "@/core/ports/fakes/fake-nutrisho-client";
import { createFakeSettingsStore } from "@/core/ports/fakes/fake-settings-store";
import {
  choicesFrom,
  defaultsFor,
  type ModelChoices,
  type ModelSetup,
} from "@/core/model-settings";
import { createFakeLineModel } from "@/core/ports/fakes/fake-line-model";
import { createFakeModelSettingsStore } from "@/core/ports/fakes/fake-model-settings-store";
import type {
  ClippingStore,
  DraftStore,
  LineModel,
  ModelSettingsStore,
  NutrishoClient,
} from "@/core/ports/types";
import { EMPTY_ROW } from "@/core/ingredient-line";
import { withDetails, withOpenGroup } from "@/core/recipe-draft";
import { err, ok } from "@/core/result";
import { EMPTY_VOCABULARY, parseVocabulary } from "@/core/vocabulary";
import type { LogEntry } from "@/nutrisho/fetch-log";

import { apiExample } from "../../tests/support/api-examples";

import Sidebar from "./Sidebar.svelte";

const CLIPPING = clippingFrom(
  {
    text: "2 aubergines\n1 tbsp olive oil",
    title: "Melanzane — Example",
    url: "https://example.test/melanzane",
    warnings: [],
  },
  new Date("2026-11-20T09:30:00Z"),
  // The blurb, so the draft has no rows a save would stop on.
  "blurb",
);

const COOKS_LISTS = parseVocabulary(
  apiExample("vocabulary.json").response.body,
);

function renderSidebar(
  overrides: {
    clippings?: ClippingStore;
    drafts?: DraftStore;
    client?: NutrishoClient;
    openSettings?: () => void;
    newSession?: boolean;
    log?: readonly LogEntry[];
    model?: LineModel;
    modelFor?: (setup: ModelSetup) => LineModel;
    modelSettings?: ModelSettingsStore;
  } = {},
) {
  let changed: (() => void) | undefined;
  let modelChanged: (() => void) | undefined;
  const client = overrides.client ?? createFakeNutrishoClient();
  let made = 0;
  const props = {
    clippings: overrides.clippings ?? createFakeClippingStore(),
    drafts: overrides.drafts ?? createFakeDraftStore(),
    newId: () => `draft-${(made += 1)}`,
    subscribe: (listener: () => void) => {
      changed = listener;
      return () => {};
    },
    client,
    openSettings: overrides.openSettings ?? vi.fn(),
    isNewSession: async () => overrides.newSession ?? false,
    settings: createFakeSettingsStore(),
    requestHostPermission: async () => true,
    log: overrides.log ?? [],
    model: overrides.model ?? createFakeLineModel(),
    modelFor: overrides.modelFor ?? (() => createFakeLineModel()),
    modelSettings: overrides.modelSettings ?? createFakeModelSettingsStore(),
    watchModelSettings: (listener: () => void) => {
      modelChanged = listener;
      return () => {};
    },
  };
  render(Sidebar, props);
  return {
    ...props,
    changed: () => changed?.(),
    modelChanged: () => modelChanged?.(),
  };
}

function answering(
  answer: Parameters<
    ReturnType<typeof createFakeNutrishoClient>["answerVocabulary"]
  >[0],
) {
  const client = createFakeNutrishoClient();
  client.answerVocabulary(answer);
  return client;
}

describe("the clipping", () => {
  it("says how to clip when nothing is clipped yet", async () => {
    renderSidebar();

    expect(
      screen.getByRole("heading", { name: "Nutrisho clipper" }),
    ).toBeVisible();
    expect(await screen.findByText("Nothing clipped yet.")).toBeVisible();
    expect(screen.getByText(/Alt\+Shift\+N/)).toBeVisible();
  });

  // Plan 012, M12: the site's lineout plate, as on its login page.
  it("shows the lineout plate while nothing is clipped", async () => {
    renderSidebar();

    expect(
      await screen.findByRole("img", { name: /rugby lineout/ }),
    ).toHaveAttribute("src", "/img/plate-lineout.webp");
  });

  it("marks Save as the main action", async () => {
    renderSidebar({
      clippings: createFakeClippingStore(CLIPPING),
      drafts: createFakeDraftStore(clipped()),
    });

    expect(await screen.findByRole("button", { name: "Clip" })).toHaveClass(
      "primary",
    );
  });

  it("says where the clipped text came from", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });

    expect(
      await screen.findByRole("link", { name: "Melanzane — Example" }),
    ).toHaveAttribute("href", "https://example.test/melanzane");
  });

  // M12: the clipboard went, so nothing shows the clipped text on its own.
  it("has no clipboard", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });
    await nameField();

    expect(screen.queryByRole("textbox", { name: "Clipboard" })).toBeNull();
    expect(screen.queryByText("Clipboard")).toBeNull();
  });

  // The sidebar is usually open already when the next capture happens.
  it("shows a new clipping as soon as one is stored", async () => {
    const clippings = createFakeClippingStore();
    const { changed } = renderSidebar({ clippings });
    await screen.findByText("Nothing clipped yet.");

    await clippings.save(CLIPPING);
    changed();

    expect(
      await screen.findByRole("link", { name: "Melanzane — Example" }),
    ).toBeVisible();
    expect(await nameField()).toHaveValue("Melanzane — Example");
  });

  it("says what could not be read off the page", async () => {
    const partial: Clipping = {
      ...CLIPPING,
      warnings: [
        { kind: "no-content-script", message: "cannot access about:reader" },
      ],
    };

    renderSidebar({ clippings: createFakeClippingStore(partial) });

    expect(await screen.findByText(/cannot access about:reader/)).toBeVisible();
  });

  it("says when the clipping could not be read", async () => {
    const clippings = createFakeClippingStore();
    clippings.failWith({ kind: "read-failed", message: "storage is gone" });

    renderSidebar({ clippings });

    expect(await screen.findByText(/storage is gone/)).toBeVisible();
  });
});

/** Wait until the lists have been asked for so often, and have come. */
async function listsLoaded(client: { readonly calls: number }, times = 1) {
  await vi.waitFor(() => expect(client.calls).toBe(times));
  await tick();
}

describe("the lists", () => {
  // They are what the clipper knows, not what the user reads: the requests
  // are in Advanced Mode's log, and only a problem is shown (#179).
  it("loads them when it opens, and shows nothing while they are fine", async () => {
    const client = answering(COOKS_LISTS);

    renderSidebar({ client });

    await listsLoaded(client);
    expect(screen.queryByRole("heading", { name: "Your lists" })).toBeNull();
    expect(screen.queryByText(/Lists loaded/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says what went wrong, and sends a key problem to the settings", async () => {
    const openSettings = vi.fn();
    renderSidebar({
      client: answering(err({ kind: "no-key", message: "no key" })),
      openSettings,
    });

    expect(await screen.findByText("No API key is saved yet.")).toBeVisible();
    await fireEvent.click(
      screen.getByRole("button", { name: "Open settings" }),
    );
    expect(openSettings).toHaveBeenCalledTimes(1);
  });

  it("tries again when asked, after a server that did not answer", async () => {
    const client = answering(
      err({ kind: "unreachable", message: "NetworkError" }),
    );
    renderSidebar({ client });
    await screen.findByText("Nothing answered at your Nutrisho's address.");

    client.answerVocabulary(COOKS_LISTS);
    await fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await listsLoaded(client, 2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the log it is given in Advanced Mode, folded away", async () => {
    renderSidebar({
      log: [{ at: new Date(), text: "← 200 OK · 15 B · 42 ms" }],
    });

    const log = await screen.findByRole("log", { name: "Log" });
    expect(log).toHaveTextContent("← 200 OK · 15 B · 42 ms");
    expect(log).not.toBeVisible();
    await fireEvent.click(screen.getByText("Advanced Mode"));
    expect(log).toBeVisible();
  });
});

const RAGU = clippingFrom(
  {
    text: "Brown the meat.",
    title: "Ragù",
    url: "https://example.test/ragu",
    warnings: [],
  },
  new Date("2026-11-20T09:40:00Z"),
);

/** The drafts a clipping of the melanzane page leaves. */
function clipped(): Drafts {
  return afterClip(EMPTY_DRAFTS, CLIPPING, () => "draft-0", EMPTY_VOCABULARY);
}

// Rows start folded to one line (#184); a row's fields show once opened.
async function openRow(n: number) {
  await fireEvent.click(
    await screen.findByRole("button", { name: `Edit row ${n}` }),
  );
  return screen.getByRole("group", { name: `Row ${n}` });
}

async function nameField() {
  return screen.findByRole("textbox", { name: "Name" });
}

describe("the draft", () => {
  it("starts when something is clipped, named after the page, and is kept", async () => {
    const drafts = createFakeDraftStore();
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING), drafts });

    expect(await nameField()).toHaveValue("Melanzane — Example");
    const stored = await drafts.load();
    expect(stored.ok && stored.value.drafts.map((draft) => draft.id)).toEqual([
      "draft-1",
    ]);
  });

  it("is there again when the sidebar opens again", async () => {
    renderSidebar({
      clippings: createFakeClippingStore(CLIPPING),
      drafts: createFakeDraftStore(clipped()),
    });

    expect(await nameField()).toHaveValue("Melanzane — Example");
  });

  // The lists load first, so the lines are scanned against them.
  it("puts a clipping sent to the ingredients in a group, scanned against the lists", async () => {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
      client: answering(COOKS_LISTS),
    });

    await screen.findByRole("group", { name: "Row 1" });
    const first = await openRow(1);
    expect(within(first).getByRole("textbox", { name: "Qty" })).toHaveValue(
      "2",
    );
    expect(
      within(first).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveValue("aubergine");
    // Olive oil is not in the lists, but the amount and unit it starts with are.
    const second = await openRow(2);
    expect(within(second).getByRole("textbox", { name: "Qty" })).toHaveValue(
      "1",
    );
    expect(within(second).getByRole("combobox", { name: "Unit" })).toHaveValue(
      "tbsp",
    );
    expect(within(second).getByRole("textbox", { name: "Rest" })).toHaveValue(
      "olive oil",
    );
  });

  it("loads the lists again from a server picked in Advanced Mode", async () => {
    const client = createFakeNutrishoClient();
    renderSidebar({ client });
    await listsLoaded(client);
    await fireEvent.click(screen.getByText("Advanced Mode"));
    await screen.findByDisplayValue("8987");

    await fireEvent.click(
      screen.getByRole("button", { name: "Use this server" }),
    );

    await screen.findByText("Now using http://127.0.0.1:8987.");
    expect(client.calls).toBe(2);
  });

  // A clip opens the sidebar, and can land while the sidebar is still
  // loading the lists: it must go into the drafts kept, not a new one.
  it("adds a clip that lands while the lists load to the draft kept", async () => {
    const kept = withDraft(
      clipped(),
      withDetails(currentDraft(clipped())!, {
        name: "My melanzane",
        blurb: "Smoky.",
        servings: "4",
      }),
    );
    const clippings = createFakeClippingStore(CLIPPING);
    let listsArrive: ((lists: typeof COOKS_LISTS) => void) | undefined;
    const client: NutrishoClient = {
      ...answering(COOKS_LISTS),
      vocabulary: () =>
        new Promise((resolve) => {
          listsArrive = resolve;
        }),
    };
    const drafts = createFakeDraftStore(kept);
    const saved = vi.spyOn(drafts, "save");
    const { changed } = renderSidebar({ clippings, drafts, client });
    // Asked for, and not come yet.
    await vi.waitFor(() => expect(listsArrive).toBeDefined());

    await clippings.save({
      ...CLIPPING,
      target: "group",
      clippedAt: "2026-11-20T09:31:00.000Z",
    });
    changed();
    listsArrive?.(COOKS_LISTS);

    expect(await screen.findByRole("group", { name: "Row 1" })).toBeVisible();
    expect(await nameField()).toHaveValue("My melanzane");
    await fireEvent.click(
      screen.getByRole("button", { name: "Edit the details" }),
    );
    expect(screen.getByRole("textbox", { name: "Blurb" })).toHaveValue(
      "Smoky.",
    );
    expect(screen.getByRole("textbox", { name: "Servings" })).toHaveValue("4");
    expect(screen.queryByRole("combobox", { name: "Draft" })).toBeNull();
    // Never a second draft, not even for a moment.
    for (const [held] of saved.mock.calls) {
      expect(held.drafts.map((draft) => draft.id)).toEqual(["draft-0"]);
    }
  });

  it("keeps Advanced Mode below the recipe", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });

    const name = await nameField();
    const advanced = screen.getByText("Advanced Mode");
    expect(
      name.compareDocumentPosition(advanced) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps an edit", async () => {
    const drafts = createFakeDraftStore(clipped());
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING), drafts });

    await fireEvent.input(await nameField(), {
      target: { value: "Melanzane" },
    });

    const stored = await drafts.load();
    expect(stored.ok && stored.value.drafts[0]?.name).toBe("Melanzane");
  });

  it("says when the drafts could not be kept", async () => {
    const drafts = createFakeDraftStore();
    drafts.failWith({ kind: "write-failed", message: "storage is full" });

    renderSidebar({ clippings: createFakeClippingStore(CLIPPING), drafts });

    expect(await screen.findByText(/storage is full/)).toBeVisible();
  });
});

describe("more than one draft", () => {
  it("starts a new one for another page, and lists the earlier one", async () => {
    const clippings = createFakeClippingStore(CLIPPING);
    const { changed } = renderSidebar({
      clippings,
      drafts: createFakeDraftStore(clipped()),
    });
    await nameField();

    await clippings.save(RAGU);
    changed();

    expect(await nameField()).toHaveValue("Ragù");
    const list = screen.getByRole("combobox", { name: "Draft" });
    expect(
      within(list)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Melanzane — Example", "Ragù"]);

    await fireEvent.change(list, { target: { value: "draft-0" } });
    expect(await nameField()).toHaveValue("Melanzane — Example");
  });

  // Drafts outlive a browser restart, but a new session opens none of them.
  it("opens none in a new browser session, and lists the ones kept", async () => {
    renderSidebar({
      drafts: createFakeDraftStore(clipped()),
      newSession: true,
    });

    const list = await screen.findByRole("combobox", { name: "Draft" });
    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
    expect(
      within(list)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Choose a draft…", "Melanzane — Example"]);

    await fireEvent.change(list, { target: { value: "draft-0" } });
    expect(await nameField()).toHaveValue("Melanzane — Example");
  });

  it("reopens a kept draft when its page is clipped in a new session", async () => {
    renderSidebar({
      clippings: createFakeClippingStore({
        ...CLIPPING,
        clippedAt: "2026-11-21T09:30:00.000Z",
      }),
      drafts: createFakeDraftStore(clipped()),
      newSession: true,
    });

    expect(await nameField()).toHaveValue("Melanzane — Example");
    expect(screen.queryByRole("combobox", { name: "Draft" })).toBeNull();
  });

  it("discards the one on show", async () => {
    const drafts = createFakeDraftStore(clipped());
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING), drafts });
    await nameField();

    await fireEvent.click(
      screen.getByRole("button", { name: "Discard this draft" }),
    );

    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
    const stored = await drafts.load();
    expect(stored.ok && stored.value.drafts).toEqual([]);
  });
});

describe("the save", () => {
  async function ready(client = createFakeNutrishoClient()) {
    const drafts = createFakeDraftStore(clipped());
    renderSidebar({
      clippings: createFakeClippingStore(CLIPPING),
      drafts,
      client,
    });
    await nameField();
    return { client, drafts };
  }

  it("sends the draft, and offers to open the recipe", async () => {
    const { client } = await ready();

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      within(await screen.findByRole("status")).getByText(
        "Saved as Melanzane — Example.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open in Nutrisho" }),
    ).toHaveAttribute("href", "http://localhost:8987/recipes/draft-0/?edit=1");
    expect(client.sent.map((draft) => draft.id)).toEqual(["draft-0"]);
  });

  // M8: the save may have made names, so the lists load again to know them.
  it("loads the lists again after a save, keeping the ones shown meanwhile", async () => {
    const client = answering(COOKS_LISTS);
    await ready(client);
    await listsLoaded(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    await screen.findByRole("status");
    await listsLoaded(client, 2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the lists it has when loading them again fails", async () => {
    const client = answering(COOKS_LISTS);
    await ready(client);
    await listsLoaded(client);
    client.answerVocabulary(err({ kind: "unreachable", message: "gone" }));

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    await listsLoaded(client, 2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not load the lists again when the save fails", async () => {
    const client = answering(COOKS_LISTS);
    client.answerSave(err({ kind: "unreachable", message: "gone" }));
    await ready(client);
    await listsLoaded(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Nothing answered/,
    );
    expect(client.calls).toBe(1);
  });

  it("says nothing changed when the server already had it", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      ok({
        openUrl: "http://localhost:8987/recipes/draft-0/?edit=1",
        name: "Melanzane — Example",
        created: false,
        renamed: false,
        inTrash: false,
        warnings: [],
      }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await screen.findByText(/Already saved, so nothing changed/),
    ).toBeVisible();
  });

  it("passes on the server's warnings", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      ok({
        openUrl: "http://localhost:8987/recipes/draft-0/?edit=1",
        name: "Melanzane — Example (2)",
        created: true,
        renamed: true,
        inTrash: false,
        warnings: ["handful is now one of your own units."],
      }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await screen.findByText("handful is now one of your own units."),
    ).toBeVisible();
    expect(screen.getByText(/name was taken/)).toBeVisible();
  });

  // Only one group is open, so the one holding the problem is opened.
  it("opens the group that stops a save", async () => {
    const draft = currentDraft(clipped())!;
    const twoGroups = withOpenGroup(
      {
        ...draft,
        groups: [
          {
            name: "Syrup",
            rows: [{ ...EMPTY_ROW, quantity: "two", ingredient: "sugar" }],
          },
          { name: "Base", rows: [{ ...EMPTY_ROW, ingredient: "lemon" }] },
        ],
      },
      1,
    );
    renderSidebar({
      clippings: createFakeClippingStore(CLIPPING),
      drafts: createFakeDraftStore(withDraft(clipped(), twoGroups)),
    });
    await nameField();
    expect(screen.queryByRole("group", { name: "Row 1" })).not.toBeNull();
    const syrup = screen.getByRole("region", { name: "Group 1" });
    expect(within(syrup).queryByRole("textbox")).toBeNull();

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await within(syrup).findByRole("textbox", { name: "Qty" }),
    ).toBeInvalid();
  });

  it("shows what stops a save, and sends nothing", async () => {
    const { client } = await ready();
    await fireEvent.input(await nameField(), { target: { value: " " } });

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(await screen.findByText("The recipe needs a name.")).toBeVisible();
    expect(await nameField()).toBeInvalid();
    expect(client.sent).toEqual([]);
  });

  // M9 (D12): the server's limits, loaded with the lists, stop a save early.
  it("refuses text too long for its field, and sends nothing", async () => {
    const { client } = await ready(answering(COOKS_LISTS));
    await listsLoaded(client);
    await fireEvent.input(await nameField(), {
      target: { value: "x".repeat(201) },
    });

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await screen.findAllByText(
        "The name is 1 character too long: it can have 200.",
      ),
    ).not.toHaveLength(0);
    expect(client.sent).toEqual([]);
  });

  // Plan 012, M11: the field the server names is flagged in the editor, in
  // the editor's words.
  it("flags the field the server refused, in the editor's words", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      err({
        kind: "refused",
        status: 400,
        message:
          "document.recipes[0].recipe_name must be at most 200 characters.",
      }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await screen.findAllByText("The name must be at most 200 characters."),
    ).not.toHaveLength(0);
    expect(await nameField()).toBeInvalid();
    expect(client.sent).toHaveLength(1);
  });

  it("shows a refusal that names no field in the server's words", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      err({
        kind: "refused",
        status: 409,
        message: "That id is taken: make a new one for this recipe.",
      }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(
      await screen.findByText(
        "Your Nutrisho did not save the recipe: That id is taken: make a new one for this recipe.",
      ),
    ).toBeVisible();
  });

  it("sends an expired key to the settings", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      err({ kind: "key-expired", status: 401, message: "expired" }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));

    expect(await screen.findByText("Your API key has expired.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Open settings" })).toBeVisible();
  });

  it("is kept with the draft, so it still shows when the sidebar opens again", async () => {
    const { drafts } = await ready();
    await fireEvent.click(screen.getByRole("button", { name: "Clip" }));
    await screen.findByRole("link", { name: "Open in Nutrisho" });

    const stored = await drafts.load();
    expect(stored.ok && stored.value.saved["draft-0"]?.openUrl).toBe(
      "http://localhost:8987/recipes/draft-0/?edit=1",
    );
  });
});

describe("Clear all", () => {
  it("drops every draft and the clipping", async () => {
    const clippings = createFakeClippingStore(CLIPPING);
    const drafts = createFakeDraftStore(
      afterClip(clipped(), RAGU, () => "draft-ragu", EMPTY_VOCABULARY),
    );
    const { changed } = renderSidebar({ clippings, drafts });
    await nameField();

    await fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    changed();

    expect(await screen.findByText("Nothing clipped yet.")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
    const stored = await drafts.load();
    expect(stored.ok && stored.value.drafts).toEqual([]);
    const clipping = await clippings.load();
    expect(clipping.ok && clipping.value).toBeUndefined();
  });

  it("sits at the top, before Advanced Mode", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });
    await nameField();

    const clear = screen.getByRole("button", { name: "Clear all" });
    const advanced = screen.getByText("Advanced Mode");
    expect(
      clear.compareDocumentPosition(advanced) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

// Plan 012, M13 (#181): a group's lines go to the user's own model when they
// ask, and its rows replace the group's only if they pass the checks.
describe("asking the model", () => {
  const MODEL_ROWS = {
    rows: [
      { quantity: "2", ingredient: "aubergine" },
      { quantity: "1", unit: "tbsp", ingredient: "olive oil" },
    ],
  };

  async function grouped(model = createFakeLineModel()) {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
      client: answering(COOKS_LISTS),
      model,
      modelSettings: createFakeModelSettingsStore(defaultsFor("mlx")),
    });
    await screen.findByRole("group", { name: "Row 2" });
    return model;
  }

  async function ask() {
    await fireEvent.click(
      await screen.findByRole("button", {
        name: "Ask the model about group 1",
      }),
    );
  }

  it("is not offered while the built-in scan is chosen", async () => {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
    });
    await screen.findByRole("group", { name: "Row 1" });

    expect(screen.queryByRole("button", { name: /Ask the model/ })).toBeNull();
  });

  // #182: the log showed nothing of the model until it was asked.
  it("checks the model when it opens, and says so in Advanced Mode", async () => {
    const model = createFakeLineModel();
    model.answer(ok(MODEL_ROWS));
    await grouped(model);
    await fireEvent.click(screen.getByText("Advanced Mode"));

    expect(
      await screen.findByText("Your model answers at http://localhost:8080."),
    ).toBeVisible();
    expect(model.checks).toBe(1);
  });

  it("says in Advanced Mode why the model does not answer", async () => {
    const model = createFakeLineModel();
    model.answer(err({ kind: "unreachable", message: "NetworkError" }));
    await grouped(model);
    await fireEvent.click(screen.getByText("Advanced Mode"));

    expect(
      await screen.findByText(/Nothing answered at your model's address\./),
    ).toBeVisible();
  });

  it("checks nothing while the built-in scan is chosen", async () => {
    const model = createFakeLineModel();
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
      model,
    });
    await screen.findByRole("group", { name: "Row 1" });

    expect(model.checks).toBe(0);
  });

  // Seen by hand (#182): the sidebar was open while the model was saved.
  it("is offered once a model is saved while the sidebar is open", async () => {
    const modelSettings = createFakeModelSettingsStore();
    const sidebar = renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
      modelSettings,
    });
    await screen.findByRole("group", { name: "Row 1" });

    await modelSettings.save(choicesFrom(defaultsFor("mlx")));
    sidebar.modelChanged();

    expect(
      await screen.findByRole("button", {
        name: "Ask the model about group 1",
      }),
    ).toBeVisible();
  });

  it("sends the group's lines only, and takes the rows it answers", async () => {
    const model = createFakeLineModel();
    model.answer(ok(MODEL_ROWS));
    await grouped(model);

    await ask();

    expect(
      await screen.findByText("Qwen3-8B-4bit on MLX split 2 lines."),
    ).toBeVisible();
    expect(model.sent).toHaveLength(1);
    expect(model.sent[0]).toHaveLength(2);
    expect(model.sent[0]?.[1]).toContain("olive oil");
    const second = await openRow(2);
    expect(
      within(second).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveValue("olive oil");
    expect(within(second).getByRole("textbox", { name: "Rest" })).toHaveValue(
      "",
    );
  });

  it("puts the rows back on Undo", async () => {
    const model = createFakeLineModel();
    model.answer(ok(MODEL_ROWS));
    await grouped(model);
    await ask();
    await screen.findByText("Qwen3-8B-4bit on MLX split 2 lines.");

    await fireEvent.click(
      screen.getByRole("button", { name: "Undo the model's rows" }),
    );

    expect(
      within(await openRow(2)).getByRole("textbox", { name: "Rest" }),
    ).toHaveValue("olive oil");
    expect(screen.queryByText(/split 2 lines/)).toBeNull();
  });

  it("keeps the scan of a row the model made up a word for", async () => {
    const model = createFakeLineModel();
    model.answer(
      ok({
        rows: [
          MODEL_ROWS.rows[0],
          { quantity: "1", unit: "tbsp", ingredient: "rapeseed oil" },
        ],
      }),
    );
    await grouped(model);

    await ask();

    expect(
      await screen.findByText(
        "Qwen3-8B-4bit on MLX split 2 lines; 1 of its rows did not match its line, so that row is as it was.",
      ),
    ).toBeVisible();
    expect(
      within(await openRow(2)).getByRole("textbox", { name: "Rest" }),
    ).toHaveValue("olive oil");
  });

  it("keeps the scan of a row whose unit is not one of the user's", async () => {
    const model = createFakeLineModel();
    model.answer(
      ok({
        rows: [
          MODEL_ROWS.rows[0],
          { quantity: "1", unit: "olive", ingredient: "oil" },
        ],
      }),
    );
    await grouped(model);

    await ask();

    expect(
      await screen.findByText(/1 of its rows did not match its line/),
    ).toBeVisible();
  });

  it("says which rows it translated", async () => {
    const model = createFakeLineModel();
    model.answer(
      ok({
        rows: [
          // Words not in the lines, as a translation's are.
          { ...MODEL_ROWS.rows[0], ingredient: "eggplants", translated: true },
          {
            ...MODEL_ROWS.rows[1],
            ingredient: "oil of olives",
            translated: true,
          },
        ],
      }),
    );
    await grouped(model);

    await ask();

    expect(
      await screen.findByText(
        "Qwen3-8B-4bit on MLX split 2 lines, and translated 2 of them into English.",
      ),
    ).toBeVisible();
  });

  it("says why the model gave nothing, and changes nothing", async () => {
    const model = createFakeLineModel();
    model.answer(err({ kind: "unreachable", message: "NetworkError" }));
    await grouped(model);

    await ask();

    // Advanced Mode's check says so too; this is the ask's own alert.
    expect(
      await screen.findByText("Nothing answered at your model's address."),
    ).toBeVisible();
    expect(
      within(await openRow(2)).getByRole("textbox", { name: "Rest" }),
    ).toHaveValue("olive oil");
  });

  it("refuses an answer that does not fit the lines", async () => {
    const model = createFakeLineModel();
    model.answer(ok({ rows: [] }));
    await grouped(model);

    await ask();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The model answered 0 rows for 2 lines.",
    );
  });

  // Seen by hand (#182): the news was far below the button pressed.
  it("says what the model did inside the group it asked about", async () => {
    const model = createFakeLineModel();
    model.answer(ok(MODEL_ROWS));
    await grouped(model);

    await ask();

    const group = screen.getByRole("region", { name: "Group 1" });
    expect(
      await within(group).findByText("Qwen3-8B-4bit on MLX split 2 lines."),
    ).toBeVisible();
    expect(
      within(group).getByRole("button", { name: "Undo the model's rows" }),
    ).toBeVisible();
  });

  it("says why the model failed inside the group it asked about", async () => {
    const model = createFakeLineModel();
    model.answer(err({ kind: "unreachable", message: "NetworkError" }));
    await grouped(model);

    await ask();

    expect(
      await within(screen.getByRole("region", { name: "Group 1" })).findByRole(
        "alert",
      ),
    ).toHaveTextContent("Nothing answered at your model's address.");
  });

  it("says it is asking while it waits", async () => {
    const model: LineModel = {
      splitLines: () => new Promise(() => {}),
      rewriteSteps: () => new Promise(() => {}),
      check: async () => ok(undefined),
    };
    await grouped(model as ReturnType<typeof createFakeLineModel>);

    await ask();

    expect(
      screen.getByRole("button", { name: "Ask the model about group 1" }),
    ).toBeDisabled();
    expect(
      within(screen.getByRole("region", { name: "Group 1" })).getByText(
        "Asking the model…",
      ),
    ).toBeVisible();
  });
});

// #181: the method rewritten short, precise and colloquial.
describe("asking the model about the steps", () => {
  const REWRITE = {
    steps: [
      { title: "", text: "Halve the aubergines" },
      { title: "", text: "Fry in the oil" },
      { title: "", text: "Season" },
    ],
  };

  async function stepped(model = createFakeLineModel()) {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "steps" }),
      client: answering(COOKS_LISTS),
      model,
      modelSettings: createFakeModelSettingsStore(defaultsFor("anthropic")),
    });
    await screen.findByRole("button", { name: "Edit step 1" });
    return model;
  }

  /** A folded step's text (#185), less the number its line starts with. */
  function stepText(line: HTMLElement): string {
    return (line.textContent ?? "").replace(/^\s*\d+\.\s*/, "").trim();
  }

  async function ask() {
    await fireEvent.click(
      await screen.findByRole("button", {
        name: "Ask the model about the steps",
      }),
    );
  }

  it("is not offered while the built-in scan is chosen", async () => {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "steps" }),
    });
    await screen.findByRole("button", { name: "Edit step 1" });

    expect(screen.queryByRole("button", { name: /Ask the model/ })).toBeNull();
  });

  it("sends the steps, and takes the rewrite", async () => {
    const model = createFakeLineModel();
    model.answer(ok(REWRITE));
    await stepped(model);
    const sent = screen
      .getAllByRole("button", { name: /^Edit step \d+$/ })
      .map(stepText);

    await ask();

    expect(
      await screen.findByText(
        `claude-haiku-5-5 on Anthropic rewrote ${sent.length} ${sent.length === 1 ? "step" : "steps"} as 3.`,
      ),
    ).toBeVisible();
    expect(model.stepsSent[0]?.map((step) => step.text)).toEqual(sent);
    expect(model.sent).toEqual([]);
    expect(stepText(screen.getByRole("button", { name: "Edit step 3" }))).toBe(
      "Season",
    );
  });

  it("says what it did between the steps' heading and the steps", async () => {
    const model = createFakeLineModel();
    model.answer(ok(REWRITE));
    await stepped(model);

    await ask();

    const note = await screen.findByText(/on Anthropic rewrote/);
    const heading = screen.getByRole("heading", { name: "Steps" });
    const first = screen.getByRole("button", { name: "Edit step 1" });
    expect(
      heading.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      note.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("puts the steps back on Undo", async () => {
    const model = createFakeLineModel();
    model.answer(ok(REWRITE));
    await stepped(model);
    const before = stepText(
      screen.getByRole("button", { name: "Edit step 1" }),
    );
    await ask();
    await screen.findByText(/on Anthropic rewrote/);

    await fireEvent.click(
      screen.getByRole("button", { name: "Undo the model's steps" }),
    );

    expect(stepText(screen.getByRole("button", { name: "Edit step 1" }))).toBe(
      before,
    );
    expect(screen.queryByText(/on Anthropic rewrote/)).toBeNull();
  });

  it("refuses an answer of the wrong shape, and changes nothing", async () => {
    const model = createFakeLineModel();
    model.answer(ok({ steps: [] }));
    await stepped(model);
    const before = stepText(
      screen.getByRole("button", { name: "Edit step 1" }),
    );

    await ask();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The model answered no steps.",
    );
    expect(stepText(screen.getByRole("button", { name: "Edit step 1" }))).toBe(
      before,
    );
  });
});

describe("asking another model once (#183)", () => {
  const QWEN: ModelSetup = {
    ...defaultsFor("mlx"),
    id: "1",
    name: "Qwen3-8B-4bit on MLX",
  };
  const HAIKU: ModelSetup = {
    ...defaultsFor("anthropic"),
    key: "sk-ant-api03-clipper",
    id: "2",
    name: "Haiku",
  };
  const BOTH: ModelChoices = { setups: [QWEN, HAIKU], chosen: "1" };
  const ROWS = {
    rows: [
      { quantity: "2", ingredient: "aubergine" },
      { quantity: "1", unit: "tbsp", ingredient: "olive oil" },
    ],
  };

  function twoModels(target: "group" | "steps", choices = BOTH) {
    const model = createFakeLineModel();
    const other = createFakeLineModel();
    model.answer(ok(ROWS));
    other.answer(ok(ROWS));
    const modelFor = vi.fn<(setup: ModelSetup) => LineModel>(() => other);
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target }),
      client: answering(COOKS_LISTS),
      model,
      modelFor,
      modelSettings: createFakeModelSettingsStore(choices),
    });
    return { model, other, modelFor };
  }

  async function askOnce(name: string, setup: string) {
    await fireEvent.contextMenu(await screen.findByRole("button", { name }));
    await fireEvent.click(screen.getByRole("menuitem", { name: setup }));
  }

  it("asks the one picked about a group, and names it", async () => {
    const { model, other, modelFor } = twoModels("group");

    await askOnce("Ask the model about group 1", "Haiku");

    expect(await screen.findByText("Haiku split 2 lines.")).toBeVisible();
    expect(modelFor).toHaveBeenCalledWith(HAIKU);
    expect(other.sent).toHaveLength(1);
    expect(model.sent).toEqual([]);
  });

  it("lists only the models other than the default", async () => {
    twoModels("group");
    await fireEvent.contextMenu(
      await screen.findByRole("button", {
        name: "Ask the model about group 1",
      }),
    );

    expect(
      screen.getAllByRole("menuitem").map((item) => item.textContent),
    ).toEqual(["Haiku"]);
  });

  it("goes back to the default on the next click", async () => {
    const { model } = twoModels("group");
    await askOnce("Ask the model about group 1", "Haiku");
    await screen.findByText("Haiku split 2 lines.");

    await fireEvent.click(
      screen.getByRole("button", { name: "Ask the model about group 1" }),
    );

    expect(
      await screen.findByText("Qwen3-8B-4bit on MLX split 2 lines."),
    ).toBeVisible();
    expect(model.sent).toHaveLength(1);
  });

  it("is taken back by one Undo", async () => {
    twoModels("group");
    await askOnce("Ask the model about group 1", "Haiku");
    await screen.findByText("Haiku split 2 lines.");

    await fireEvent.click(
      screen.getByRole("button", { name: "Undo the model's rows" }),
    );

    expect(
      within(await openRow(2)).getByRole("textbox", { name: "Rest" }),
    ).toHaveValue("olive oil");
  });

  it("asks the one picked about the steps, and names it", async () => {
    const { model, other } = twoModels("steps");
    other.answer(ok({ steps: [{ title: "", text: "Fry it all" }] }));

    await askOnce("Ask the model about the steps", "Haiku");

    expect(
      await screen.findByText(/^Haiku rewrote \d+ steps? as 1\.$/),
    ).toBeVisible();
    expect(other.stepsSent).toHaveLength(1);
    expect(model.stepsSent).toEqual([]);
  });

  it("offers no menu with one model", async () => {
    twoModels("group", choicesFrom(defaultsFor("mlx")));
    const button = await screen.findByRole("button", {
      name: "Ask the model about group 1",
    });

    expect(button).not.toHaveAttribute("aria-haspopup");
  });
});
