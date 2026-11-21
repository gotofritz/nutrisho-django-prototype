import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { clippingFrom, type Clipping } from "@/core/clipping";
import { EMPTY_DRAFTS, afterClip, type Drafts } from "@/core/drafts";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { createFakeDraftStore } from "@/core/ports/fakes/fake-draft-store";
import { createFakeNutrishoClient } from "@/core/ports/fakes/fake-nutrisho-client";
import type {
  ClippingStore,
  DraftStore,
  NutrishoClient,
} from "@/core/ports/types";
import { err, ok } from "@/core/result";
import { EMPTY_VOCABULARY, parseVocabulary } from "@/core/vocabulary";

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
  } = {},
) {
  let changed: (() => void) | undefined;
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
  };
  render(Sidebar, props);
  return { ...props, changed: () => changed?.() };
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

  it("puts the clipped text in the clipboard, and says where it came from", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });

    expect(
      await screen.findByRole("link", { name: "Melanzane — Example" }),
    ).toHaveAttribute("href", "https://example.test/melanzane");
    expect(screen.getByRole("textbox", { name: "Clipboard" })).toHaveValue(
      "2 aubergines\n1 tbsp olive oil",
    );
  });

  // The sidebar is usually open already when the next capture happens.
  it("shows a new clipping as soon as one is stored", async () => {
    const clippings = createFakeClippingStore();
    const { changed } = renderSidebar({ clippings });
    await screen.findByText("Nothing clipped yet.");

    await clippings.save(CLIPPING);
    changed();

    expect(
      await screen.findByRole("textbox", { name: "Clipboard" }),
    ).toHaveValue("2 aubergines\n1 tbsp olive oil");
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

describe("the lists", () => {
  it("loads them when it opens, and says whose they are", async () => {
    const client = answering(COOKS_LISTS);

    renderSidebar({ client });

    expect(
      await screen.findByText(
        "Lists loaded for cook: 3 ingredients, 3 units, 2 cuisines, 2 tags.",
      ),
    ).toBeVisible();
    expect(client.calls).toBe(1);
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

    expect(await screen.findByText(/Lists loaded for cook/)).toBeVisible();
    expect(client.calls).toBe(2);
  });

  it("says it is loading while it waits", async () => {
    const client: NutrishoClient = {
      ...createFakeNutrishoClient(),
      vocabulary: () => new Promise(() => {}),
    };

    renderSidebar({ client });

    expect(await screen.findByText("Loading your lists…")).toBeVisible();
  });

  it("counts one of a kind in the singular", async () => {
    renderSidebar({
      client: answering(
        ok({
          user: "cook",
          ingredients: [{ name: "basil", spellings: [] }],
          units: [],
          cuisines: ["med"],
          tags: [],
          limits: {},
        }),
      ),
    });

    expect(
      await screen.findByText(
        "Lists loaded for cook: 1 ingredient, 0 units, 1 cuisine, 0 tags.",
      ),
    ).toBeVisible();
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

  it("scans the lines sent to the ingredients against the lists", async () => {
    renderSidebar({
      clippings: createFakeClippingStore(CLIPPING),
      client: answering(COOKS_LISTS),
    });
    await screen.findByText(/Lists loaded for cook/);

    await fireEvent.click(
      screen.getByRole("button", { name: "Add to ingredient groups" }),
    );

    const first = await screen.findByRole("group", { name: "Row 1" });
    expect(
      within(first).getByRole("textbox", { name: "Quantity" }),
    ).toHaveValue("2");
    expect(
      within(first).getByRole("textbox", { name: "Ingredient" }),
    ).toHaveValue("aubergine");
    const second = screen.getByRole("group", { name: "Row 2" });
    expect(within(second).getByRole("textbox", { name: "Rest" })).toHaveValue(
      "1 tbsp olive oil",
    );
  });

  // The right-click submenu sends the text on as well as to the clipboard.
  // The lists load first, so the lines are scanned against them.
  it("puts a clipping sent to the ingredients in a group, scanned against the lists", async () => {
    renderSidebar({
      clippings: createFakeClippingStore({ ...CLIPPING, target: "group" }),
      client: answering(COOKS_LISTS),
    });

    const first = await screen.findByRole("group", { name: "Row 1" });
    expect(
      within(first).getByRole("textbox", { name: "Ingredient" }),
    ).toHaveValue("aubergine");
    expect(screen.getByRole("textbox", { name: "Clipboard" })).toHaveValue(
      CLIPPING.text,
    );
  });

  it("keeps the clipboard below the recipe", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });

    const name = await nameField();
    const clipboard = screen.getByRole("textbox", { name: "Clipboard" });
    expect(
      name.compareDocumentPosition(clipboard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
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

  // Typed or pasted text is treated the same as clipped text (D3).
  it("starts from typed text when nothing was clipped", async () => {
    renderSidebar();
    const clipboard = await screen.findByRole("textbox", { name: "Clipboard" });

    await fireEvent.input(clipboard, { target: { value: "Lemon posset" } });
    await fireEvent.click(screen.getByRole("button", { name: "Replace name" }));

    expect(await nameField()).toHaveValue("Lemon posset");
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

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Saved as Melanzane — Example."),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open in Nutrisho" }),
    ).toHaveAttribute("href", "http://localhost:8987/recipes/draft-0/?edit=1");
    expect(client.sent.map((draft) => draft.id)).toEqual(["draft-0"]);
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

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

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

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("handful is now one of your own units."),
    ).toBeVisible();
    expect(screen.getByText(/name was taken/)).toBeVisible();
  });

  it("shows what stops a save, and sends nothing", async () => {
    const { client } = await ready();
    await fireEvent.input(await nameField(), { target: { value: " " } });

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("The recipe needs a name.")).toBeVisible();
    expect(await nameField()).toBeInvalid();
    expect(client.sent).toEqual([]);
  });

  it("shows the server's refusal as it came", async () => {
    const client = createFakeNutrishoClient();
    client.answerSave(
      err({
        kind: "refused",
        status: 400,
        message:
          "document.recipes[0].steps[0].step_text must be at most 4000 characters.",
      }),
    );
    await ready(client);

    await fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "Your Nutrisho did not save the recipe: document.recipes[0].steps[0].step_text must be at most 4000 characters.",
      ),
    ).toBeVisible();
  });

  it("is kept with the draft, so it still shows when the sidebar opens again", async () => {
    const { drafts } = await ready();
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("link", { name: "Open in Nutrisho" });

    const stored = await drafts.load();
    expect(stored.ok && stored.value.saved["draft-0"]?.openUrl).toBe(
      "http://localhost:8987/recipes/draft-0/?edit=1",
    );
  });
});

describe("Clear all", () => {
  it("empties the clipboard and drops every draft and the clipping", async () => {
    const clippings = createFakeClippingStore(CLIPPING);
    const drafts = createFakeDraftStore(
      afterClip(clipped(), RAGU, () => "draft-ragu", EMPTY_VOCABULARY),
    );
    const { changed } = renderSidebar({ clippings, drafts });
    await nameField();

    await fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    changed();

    expect(await screen.findByText("Nothing clipped yet.")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Clipboard" })).toHaveValue("");
    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
    const stored = await drafts.load();
    expect(stored.ok && stored.value.drafts).toEqual([]);
    const clipping = await clippings.load();
    expect(clipping.ok && clipping.value).toBeUndefined();
  });

  it("sits at the top, before the clipboard", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });
    await nameField();

    const clear = screen.getByRole("button", { name: "Clear all" });
    const clipboard = screen.getByRole("textbox", { name: "Clipboard" });
    expect(
      clear.compareDocumentPosition(clipboard) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
