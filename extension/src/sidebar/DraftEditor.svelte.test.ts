import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_ROW } from "@/core/ingredient-line";
import { startDraft, type RecipeDraft } from "@/core/recipe-draft";
import { EMPTY_VOCABULARY, type Vocabulary } from "@/core/vocabulary";

import DraftEditor from "./DraftEditor.svelte";

const LISTS: Vocabulary = {
  ...EMPTY_VOCABULARY,
  ingredients: [{ name: "lemon", spellings: ["lemons"] }],
  units: [{ name: "g", spellings: ["grams"] }],
};

const DRAFT: RecipeDraft = {
  ...startDraft({
    id: "01a1f5b5-dbe2-704a-b591-7ffbcff6762e",
    title: "Lemon tart",
    url: "https://example.test/tart",
    now: "2026-11-20T09:30:00.000Z",
  }),
  groups: [
    {
      name: "",
      rows: [
        { ...EMPTY_ROW, quantity: "2", ingredient: "lemon", rest: "Juice of" },
        { ...EMPTY_ROW, quantity: "1", unit: "handful", ingredient: "boletus" },
      ],
    },
    { name: "For the syrup", rows: [{ ...EMPTY_ROW, ingredient: "lemon" }] },
  ],
  steps: ["Zest the lemons.", "Bake."],
};

function renderEditor(draft: RecipeDraft = DRAFT, issues = []) {
  const onChange = vi.fn<(draft: RecipeDraft) => void>();
  render(DraftEditor, { draft, vocabulary: LISTS, issues, onChange });
  return { onChange, changed: () => onChange.mock.lastCall?.[0] };
}

describe("the recipe's details", () => {
  it("shows the name, blurb, servings and source, and edits each", async () => {
    const { changed } = renderEditor();

    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue(
      "Lemon tart",
    );
    expect(screen.getByRole("textbox", { name: "Source" })).toHaveValue(
      "https://example.test/tart",
    );

    await fireEvent.input(screen.getByRole("textbox", { name: "Servings" }), {
      target: { value: "8" },
    });
    expect(changed()?.servings).toBe("8");

    await fireEvent.input(screen.getByRole("textbox", { name: "Blurb" }), {
      target: { value: "Sharp." },
    });
    expect(changed()?.blurb).toBe("Sharp.");
  });
});

/** A row of the first group, as the user finds it. */
function row(number: number, group = 1) {
  return within(
    screen.getByRole("region", { name: `Group ${group}` }),
  ).getByRole("group", { name: `Row ${number}` });
}

describe("the ingredient groups", () => {
  it("shows each group's name, and edits it", async () => {
    const { changed } = renderEditor();

    const second = screen.getByRole("region", { name: "Group 2" });
    const name = within(second).getByRole("textbox", { name: "Group name" });
    expect(name).toHaveValue("For the syrup");

    await fireEvent.input(name, { target: { value: "Syrup" } });
    expect(changed()?.groups[1]?.name).toBe("Syrup");
    expect(changed()?.groups[0]).toBe(DRAFT.groups[0]);
  });
});

describe("the ingredient rows", () => {
  it("shows each row's fields, rest included", () => {
    renderEditor();

    const first = row(1);
    expect(
      within(first).getByRole("textbox", { name: "Quantity" }),
    ).toHaveValue("2");
    expect(
      within(first).getByRole("textbox", { name: "Ingredient" }),
    ).toHaveValue("lemon");
    expect(within(first).getByRole("textbox", { name: "Rest" })).toHaveValue(
      "Juice of",
    );
    for (const field of ["Unit", "Substitute", "Preparation", "Note"]) {
      expect(within(first).getByRole("textbox", { name: field })).toHaveValue(
        "",
      );
    }
  });

  it("edits any field of a row", async () => {
    const { changed } = renderEditor();

    const second = row(2);
    await fireEvent.input(
      within(second).getByRole("textbox", { name: "Preparation" }),
      {
        target: { value: "sliced" },
      },
    );

    expect(changed()?.groups[0]?.rows[1]).toMatchObject({
      ingredient: "boletus",
      preparation: "sliced",
    });
    expect(changed()?.groups[0]?.rows[0]).toBe(DRAFT.groups[0]?.rows[0]);
  });

  it("marks an ingredient or unit the lists do not hold as new", () => {
    renderEditor();

    const first = row(1);
    const second = row(2);
    expect(within(first).queryByText("new")).toBeNull();
    expect(within(second).getAllByText("new")).toHaveLength(2);
    expect(
      within(second).getByRole("textbox", { name: "Ingredient" }),
    ).toHaveAccessibleDescription("new: saving makes it one of your own");
  });

  it("says there are none yet", () => {
    renderEditor({ ...DRAFT, groups: [] });

    expect(screen.getByText(/No ingredients yet/)).toBeVisible();
  });
});

describe("the steps", () => {
  it("shows each step, and edits one", async () => {
    const { changed } = renderEditor();

    expect(screen.getByRole("textbox", { name: "Step 1" })).toHaveValue(
      "Zest the lemons.",
    );
    await fireEvent.input(screen.getByRole("textbox", { name: "Step 2" }), {
      target: { value: "Bake for 30 minutes." },
    });

    expect(changed()?.steps).toEqual([
      "Zest the lemons.",
      "Bake for 30 minutes.",
    ]);
  });
});

describe("what stops a save", () => {
  it("marks the field each issue is in", () => {
    render(DraftEditor, {
      draft: DRAFT,
      vocabulary: LISTS,
      issues: [
        { field: "name", message: "The recipe needs a name." },
        {
          field: "groups.0.rows.1.ingredient",
          message: "Row 2 has no ingredient.",
        },
      ],
      onChange: vi.fn(),
    });

    expect(screen.getByRole("textbox", { name: "Name" })).toBeInvalid();
    const second = row(2);
    expect(
      within(second).getByRole("textbox", { name: "Ingredient" }),
    ).toBeInvalid();
    expect(
      within(second).getByRole("textbox", { name: "Quantity" }),
    ).toBeValid();
  });
});
