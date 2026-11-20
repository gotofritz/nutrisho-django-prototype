import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { clippingFrom, type Clipping } from "@/core/clipping";
import { createFakeClippingStore } from "@/core/ports/fakes/fake-clipping-store";
import { createFakeNutrishoClient } from "@/core/ports/fakes/fake-nutrisho-client";
import type { ClippingStore, NutrishoClient } from "@/core/ports/types";
import { err, ok } from "@/core/result";
import { parseVocabulary } from "@/core/vocabulary";

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
    client?: NutrishoClient;
    openSettings?: () => void;
  } = {},
) {
  let changed: (() => void) | undefined;
  const client = overrides.client ?? createFakeNutrishoClient();
  const props = {
    clippings: overrides.clippings ?? createFakeClippingStore(),
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

  it("shows the clipped text a line at a time, and where it came from", async () => {
    renderSidebar({ clippings: createFakeClippingStore(CLIPPING) });

    const lines = await screen.findAllByRole("listitem");
    expect(lines.map((line) => line.textContent)).toEqual([
      "2 aubergines",
      "1 tbsp olive oil",
    ]);
    expect(
      screen.getByRole("link", { name: "Melanzane — Example" }),
    ).toHaveAttribute("href", "https://example.test/melanzane");
  });

  // The sidebar is usually open already when the next capture happens.
  it("shows a new clipping as soon as one is stored", async () => {
    const clippings = createFakeClippingStore();
    const { changed } = renderSidebar({ clippings });
    await screen.findByText("Nothing clipped yet.");

    await clippings.save(CLIPPING);
    changed();

    expect(await screen.findByText("1 tbsp olive oil")).toBeVisible();
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
    const client: NutrishoClient = { vocabulary: () => new Promise(() => {}) };

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
