import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_ROW } from "@/core/ingredient-line";
import {
  startDraft,
  withOpenGroup,
  type RecipeDraft,
} from "@/core/recipe-draft";
import { EMPTY_VOCABULARY, type Vocabulary } from "@/core/vocabulary";

import DraftEditor from "./DraftEditor.svelte";

const LISTS: Vocabulary = {
  ...EMPTY_VOCABULARY,
  ingredients: [{ name: "lemon", spellings: ["lemons"] }],
  units: [{ name: "g", spellings: ["grams"] }],
  cuisines: ["med", "med.italy", "med.italy.sicily"],
  tags: ["dinner", "quick"],
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
  openGroup: 0,
  steps: [
    { title: "The lemons", text: "Zest the lemons." },
    { title: "", text: "Bake." },
  ],
};

/** An editor whose every change comes back as its draft, as in the sidebar. */
function renderLiveEditor(draft: RecipeDraft = DRAFT) {
  const onChange = vi.fn<(draft: RecipeDraft) => void>();
  const { rerender } = render(DraftEditor, {
    draft,
    vocabulary: LISTS,
    issues: [],
    onChange,
  });
  onChange.mockImplementation((changed) => void rerender({ draft: changed }));
  return { changed: () => onChange.mock.lastCall?.[0] };
}

function renderEditor(draft: RecipeDraft = DRAFT, issues = []) {
  const onChange = vi.fn<(draft: RecipeDraft) => void>();
  render(DraftEditor, { draft, vocabulary: LISTS, issues, onChange });
  return { onChange, changed: () => onChange.mock.lastCall?.[0] };
}

/** Open the folded details under the name (#185), as the user taps them. */
async function openDetails() {
  await fireEvent.click(
    screen.getByRole("button", { name: "Edit the details" }),
  );
}

/** Open a folded step (#185), as the user taps its line. */
async function openStep(number: number) {
  await fireEvent.click(
    screen.getByRole("button", { name: `Edit step ${number}` }),
  );
}

describe("the recipe's details", () => {
  it("shows the name, blurb, servings and source, and edits each", async () => {
    const { changed } = renderEditor();

    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue(
      "Lemon tart",
    );
    await openDetails();
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

  // #185: the details fold under the name, as a recipe's byline reads.
  it("folds all but the name to one line and the blurb, and opens them", async () => {
    renderEditor({
      ...DRAFT,
      servings: "4",
      cuisine: "med.italy.sicily",
      tags: ["dinner", " quick"],
      blurb: "Sharp and sweet.",
    });

    expect(screen.getByRole("textbox", { name: "Name" })).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Servings" })).toBeNull();
    const line = screen.getByRole("button", { name: "Edit the details" });
    expect(line).toHaveTextContent(
      "Serves 4 · med.italy.sicily · dinner, quick · example.test",
    );
    expect(line).toHaveTextContent("Sharp and sweet.");
    expect(line).toHaveAttribute("aria-expanded", "false");

    await fireEvent.click(line);

    expect(screen.getByRole("textbox", { name: "Servings" })).toHaveValue("4");
    const fold = screen.getByRole("button", { name: "Fold the details" });
    expect(fold).toHaveAttribute("aria-expanded", "true");
    await fireEvent.click(fold);
    expect(screen.queryByRole("textbox", { name: "Servings" })).toBeNull();
  });

  it("says when there are no details yet", () => {
    renderEditor({ ...DRAFT, source: "" });

    expect(
      screen.getByRole("button", { name: "Edit the details" }),
    ).toHaveTextContent("No servings, cuisine or tags yet");
  });

  it("opens the details when one stops a save", () => {
    render(DraftEditor, {
      draft: DRAFT,
      vocabulary: LISTS,
      issues: [{ field: "servings", message: "Servings must be a number." }],
      onChange: vi.fn(),
    });

    expect(screen.getByRole("textbox", { name: "Servings" })).toBeInvalid();
  });

  it("marks a new tag or cuisine on the folded line", () => {
    renderEditor({ ...DRAFT, tags: ["fika"] });

    expect(
      screen.getByRole("button", { name: "Edit the details" }),
    ).toHaveTextContent("fika · example.test new");
  });

  it("folds an open row when the details open, one thing at a time", async () => {
    renderEditor();
    await edit(1);

    await openDetails();

    expect(within(row(1)).queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Servings" })).toBeVisible();
  });
});

/** A row of the first group, as the user finds it. */
function row(number: number, group = 1) {
  return within(
    screen.getByRole("region", { name: `Group ${group}` }),
  ).getByRole("group", { name: `Row ${number}` });
}

/** Open a folded row, as the user taps its line, and give it back. */
async function edit(number: number, group = 1) {
  await fireEvent.click(
    within(row(number, group)).getByRole("button", {
      name: `Edit row ${number}`,
    }),
  );
  return row(number, group);
}

describe("the source", () => {
  it("opens in a new tab of the browser", async () => {
    renderEditor();
    await openDetails();

    const open = screen.getByRole("link", { name: "Open the source" });
    expect(open).toHaveAttribute("href", "https://example.test/tart");
    expect(open).toHaveAttribute("target", "_blank");
  });

  it.each(["", "Moro, p. 112", "javascript:alert(1)"])(
    "is not a link when it is %j",
    (source) => {
      renderEditor({ ...DRAFT, source });

      expect(
        screen.queryByRole("link", { name: "Open the source" }),
      ).toBeNull();
    },
  );
});

/** The names a field with a list offers, in order. */
function offered(input: HTMLElement): string[] {
  const list = document.getElementById(input.getAttribute("list") ?? "");
  return [...(list?.querySelectorAll("option") ?? [])].map(
    (option) => option.value,
  );
}

// M8: typing in a field offers the names in the loaded lists.
describe("names from the lists", () => {
  it("offers the ingredients for an ingredient or substitute, the units for a unit", async () => {
    renderEditor();

    const first = await edit(1);
    expect(
      offered(within(first).getByRole("combobox", { name: "Ingredient" })),
    ).toEqual(["lemon"]);
    expect(
      offered(within(first).getByRole("combobox", { name: "Substitute" })),
    ).toEqual(["lemon"]);
    expect(
      offered(within(first).getByRole("combobox", { name: "Unit" })),
    ).toEqual(["g"]);
  });

  it("marks a substitute the lists do not hold as new", async () => {
    renderEditor({
      ...DRAFT,
      groups: [
        {
          name: "",
          rows: [{ ...EMPTY_ROW, ingredient: "lemon", substitute: "lime" }],
        },
      ],
    });

    expect(
      within(await edit(1)).getByRole("combobox", { name: "Substitute" }),
    ).toHaveAccessibleDescription("new: saving makes it one of your own");
  });
});

describe("the cuisine", () => {
  it("offers the cuisine tree's paths, and edits the cuisine", async () => {
    const { changed } = renderEditor();
    await openDetails();

    const cuisine = screen.getByRole("combobox", { name: "Cuisine" });
    expect(offered(cuisine)).toEqual(["med", "med.italy", "med.italy.sicily"]);

    await fireEvent.input(cuisine, { target: { value: "sicily" } });
    expect(changed()?.cuisine).toBe("sicily");
  });

  it("marks a cuisine the tree does not hold as new", async () => {
    renderEditor({ ...DRAFT, cuisine: "med.italy.marche" });
    await openDetails();

    expect(
      screen.getByRole("combobox", { name: "Cuisine" }),
    ).toHaveAccessibleDescription("new: saving makes it one of your own");
  });

  it("does not mark a cuisine the tree holds", async () => {
    renderEditor({ ...DRAFT, cuisine: "Sicily" });
    await openDetails();

    expect(
      screen.getByRole("combobox", { name: "Cuisine" }),
    ).not.toHaveAccessibleDescription();
  });
});

describe("the tags", () => {
  it("shows the tags comma-separated, and edits them as typed", async () => {
    const { changed } = renderEditor({ ...DRAFT, tags: ["dinner", " quick"] });
    await openDetails();

    const tags = screen.getByRole("textbox", { name: "Tags" });
    expect(tags).toHaveValue("dinner, quick");

    await fireEvent.input(tags, { target: { value: "dinner, ice cream, " } });
    expect(changed()?.tags).toEqual(["dinner", " ice cream", " "]);
  });

  it("names the tags the lists do not hold as new", async () => {
    renderEditor({ ...DRAFT, tags: ["Dinner", " ice cream", " fika"] });
    await openDetails();

    expect(
      screen.getByRole("textbox", { name: "Tags" }),
    ).toHaveAccessibleDescription(
      "new: ice cream, fika: saving makes them your own",
    );
  });

  it("marks nothing when every tag is known", async () => {
    renderEditor({ ...DRAFT, tags: ["dinner", " quick"] });
    await openDetails();

    expect(
      screen.getByRole("textbox", { name: "Tags" }),
    ).not.toHaveAccessibleDescription();
  });
});

describe("the ingredient groups", () => {
  it("shows each group's name, and edits it", async () => {
    const { changed } = renderEditor({ ...DRAFT, openGroup: 1 });

    const second = screen.getByRole("region", { name: "Group 2" });
    const name = within(second).getByRole("textbox", { name: "Group name" });
    expect(name).toHaveValue("For the syrup");

    await fireEvent.input(name, { target: { value: "Syrup" } });
    expect(changed()?.groups[1]?.name).toBe("Syrup");
    expect(changed()?.groups[0]).toBe(DRAFT.groups[0]);
  });
});

describe("a whole group", () => {
  const group = (number: number) =>
    screen.getByRole("region", { name: `Group ${number}` });

  it("is deleted, rows and all", async () => {
    const { changed } = renderEditor();

    await fireEvent.click(
      within(group(1)).getByRole("button", { name: "Delete group 1" }),
    );

    expect(changed()?.groups).toEqual([DRAFT.groups[1]]);
  });

  // One group open at a time, so a long list of ingredients scrolls less.
  it("shows one group open, the others as their name and rows", () => {
    renderEditor();

    expect(within(group(1)).getAllByRole("group")).toHaveLength(2);
    expect(within(group(2)).queryByRole("textbox")).toBeNull();
    expect(within(group(2)).getByText("For the syrup · 1 row")).toBeVisible();
    const toggle = within(group(2)).getByRole("button", {
      name: "Collapse group 2",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent("▼");
  });

  it("opens another group, and closes the one open", async () => {
    const { changed } = renderLiveEditor();

    await fireEvent.click(
      within(group(2)).getByRole("button", { name: "Collapse group 2" }),
    );

    expect(changed()?.openGroup).toBe(1);
    expect(
      within(group(2)).getByRole("textbox", { name: "Group name" }),
    ).toBeVisible();
    expect(within(group(1)).getByText("Unnamed group · 2 rows")).toBeVisible();
  });

  it("closes the open group, leaving none open", async () => {
    const { changed } = renderLiveEditor();

    const toggle = within(group(1)).getByRole("button", {
      name: "Collapse group 1",
    });
    expect(toggle).toHaveTextContent("▲");
    await fireEvent.click(toggle);

    expect(changed()?.openGroup).toBeUndefined();
    expect(screen.queryByRole("group", { name: "Row 1" })).toBeNull();
  });
});

describe("adding ingredients", () => {
  it("adds a group below the others", async () => {
    const { changed } = renderEditor();

    await fireEvent.click(
      screen.getByRole("button", { name: "Add an ingredient group" }),
    );

    expect(changed()?.groups).toEqual([
      ...DRAFT.groups,
      { name: "", rows: [EMPTY_ROW] },
    ]);
  });

  it("adds a group when there are none", async () => {
    const { changed } = renderEditor({ ...DRAFT, groups: [] });

    await fireEvent.click(
      screen.getByRole("button", { name: "Add an ingredient group" }),
    );

    expect(changed()?.groups).toHaveLength(1);
  });

  it("adds an ingredient at the end of the open group", async () => {
    const { changed } = renderEditor({ ...DRAFT, openGroup: 1 });

    await fireEvent.click(
      within(screen.getByRole("region", { name: "Group 2" })).getByRole(
        "button",
        { name: "Add an ingredient to group 2" },
      ),
    );

    expect(changed()?.groups[0]).toBe(DRAFT.groups[0]);
    expect(changed()?.groups[1]?.rows).toEqual([
      ...DRAFT.groups[1]!.rows,
      EMPTY_ROW,
    ]);
  });
});

describe("the ingredient rows", () => {
  it("shows each row's fields, rest included", async () => {
    renderEditor();

    const first = await edit(1);
    expect(within(first).getByRole("textbox", { name: "Qty" })).toHaveValue(
      "2",
    );
    expect(
      within(first).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveValue("lemon");
    expect(within(first).getByRole("textbox", { name: "Rest" })).toHaveValue(
      "Juice of",
    );
    for (const field of ["Preparation", "Note"]) {
      expect(within(first).getByRole("textbox", { name: field })).toHaveValue(
        "",
      );
    }
    for (const field of ["Unit", "Substitute"]) {
      expect(within(first).getByRole("combobox", { name: field })).toHaveValue(
        "",
      );
    }
  });

  it("edits any field of a row", async () => {
    const { changed } = renderEditor();

    const second = await edit(2);
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

  it("marks an ingredient or unit the lists do not hold as new", async () => {
    renderEditor();

    // Folded, a row with a new name says so on its line.
    expect(within(row(1)).queryByText("new")).toBeNull();
    expect(within(row(2)).getByText("new")).toBeVisible();
    const second = await edit(2);
    expect(within(second).getAllByText("new")).toHaveLength(2);
    expect(
      within(second).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveAccessibleDescription("new: saving makes it one of your own");
  });

  it("deletes a row", async () => {
    const { changed } = renderEditor();

    await edit(1);
    await fireEvent.click(
      within(row(1)).getByRole("button", { name: "Delete row 1" }),
    );

    expect(changed()?.groups[0]?.rows).toEqual([DRAFT.groups[0]?.rows[1]]);
  });

  // #184: a row has seven fields, so a long list meant a lot of scrolling.
  // Each row reads as one line, as a recipe prints it, until it is opened.
  it("shows each row as one line, and opens one to edit", async () => {
    renderEditor();

    expect(within(row(1)).queryByRole("textbox")).toBeNull();
    expect(within(row(1)).queryByRole("combobox")).toBeNull();
    const line = within(row(1)).getByRole("button", { name: "Edit row 1" });
    expect(line).toHaveTextContent("2 lemon · Juice of");
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(
      within(row(2)).getByRole("button", { name: "Edit row 2" }),
    ).toHaveTextContent("1 handful boletus");

    await fireEvent.click(line);

    // Quantity, preparation, note and rest; unit, ingredient and substitute.
    expect(within(row(1)).getAllByRole("textbox")).toHaveLength(4);
    expect(within(row(1)).getAllByRole("combobox")).toHaveLength(3);
    const fold = within(row(1)).getByRole("button", { name: "Fold row 1" });
    expect(fold).toHaveAttribute("aria-expanded", "true");

    await fireEvent.click(fold);
    expect(within(row(1)).queryByRole("textbox")).toBeNull();
  });

  it("opens one row at a time", async () => {
    renderEditor();

    await edit(1);
    await edit(2);

    expect(within(row(1)).queryByRole("textbox")).toBeNull();
    expect(within(row(2)).getAllByRole("textbox")).toHaveLength(4);
  });

  it("calls an empty row empty", () => {
    renderEditor({
      ...DRAFT,
      groups: [{ name: "", rows: [EMPTY_ROW] }],
    });

    expect(
      within(row(1)).getByRole("button", { name: "Edit row 1" }),
    ).toHaveTextContent("Empty row");
  });

  it("opens the row it adds", async () => {
    renderLiveEditor();

    await fireEvent.click(
      screen.getByRole("button", { name: "Add an ingredient to group 1" }),
    );

    expect(within(row(3)).getAllByRole("textbox")).toHaveLength(4);
    expect(within(row(1)).queryByRole("textbox")).toBeNull();
  });

  it("keeps the open row open as it moves", async () => {
    renderLiveEditor();

    await edit(2);
    await fireEvent.click(
      within(row(2)).getByRole("button", { name: "Move row 2 up" }),
    );

    expect(
      within(row(1)).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveValue("boletus");
    expect(within(row(2)).queryByRole("textbox")).toBeNull();
  });

  // Rest is a scratch pad: what is wanted is moved to a field.
  it("says rest is not saved, and clears it", async () => {
    const { changed } = renderEditor();
    await edit(1);

    const rest = within(row(1)).getByRole("textbox", { name: "Rest" });
    expect(rest).toHaveAccessibleDescription("Not saved");
    await fireEvent.click(
      within(row(1)).getByRole("button", { name: "Clear rest of row 1" }),
    );

    expect(changed()?.groups[0]?.rows[0]).toMatchObject({
      ingredient: "lemon",
      rest: "",
    });
  });

  // #202: note and substitute, the two boxes and preparation, then rest
  // across the row, under quantity, unit and ingredient.
  it("lays a row out as the note, the boxes, preparation and rest", async () => {
    renderEditor();
    const first = await edit(1);

    const fields = [
      ...first.querySelectorAll<HTMLInputElement>(".fields input"),
    ].map((input) =>
      input.type === "checkbox"
        ? (input.closest("label")?.textContent?.trim() ?? "")
        : (input.labels?.[0]?.firstChild?.textContent?.trim() ?? ""),
    );
    expect(fields).toEqual([
      "Qty",
      "Unit",
      "Ingredient",
      "Note",
      "Substitute",
      "to taste",
      "optional",
      "Preparation",
      "Rest",
    ]);
  });

  // #202: ticked, each goes into the note; unticked, it comes out.
  it.each(["to taste", "optional"])(
    "ticks %s into the note, and out of it",
    async (flag) => {
      const { changed } = renderLiveEditor({
        ...DRAFT,
        groups: [
          {
            name: "",
            rows: [{ ...EMPTY_ROW, ingredient: "lemon", note: "for garnish" }],
          },
        ],
      });
      const first = await edit(1);
      const box = within(first).getByRole("checkbox", { name: flag });
      expect(box).not.toBeChecked();

      await fireEvent.click(box);
      expect(changed()?.groups[0]?.rows[0]?.note).toBe(`for garnish, ${flag}`);
      expect(
        within(row(1)).getByRole("checkbox", { name: flag }),
      ).toBeChecked();

      await fireEvent.click(
        within(row(1)).getByRole("checkbox", { name: flag }),
      );
      expect(changed()?.groups[0]?.rows[0]?.note).toBe("for garnish");
    },
  );

  it("ticks a box the note already says", async () => {
    renderEditor({
      ...DRAFT,
      groups: [
        {
          name: "",
          rows: [{ ...EMPTY_ROW, ingredient: "salt", note: "To taste" }],
        },
      ],
    });
    const first = await edit(1);

    expect(
      within(first).getByRole("checkbox", { name: "to taste" }),
    ).toBeChecked();
    expect(
      within(first).getByRole("checkbox", { name: "optional" }),
    ).not.toBeChecked();
  });

  // #202: Rest (Prep, Sub, Note), each word copying rest to that field.
  it.each([
    ["Prep", "preparation"],
    ["Sub", "substitute"],
    ["Note", "note"],
  ] as const)("copies rest to the field %s names", async (word, field) => {
    const { changed } = renderEditor();
    const first = await edit(1);

    const copy = within(first).getByRole("button", {
      name: `Copy rest of row 1 to ${field}`,
    });
    expect(copy).toHaveTextContent(word);
    await fireEvent.click(copy);

    expect(changed()?.groups[0]?.rows[0]).toMatchObject({
      [field]: "Juice of",
      rest: "Juice of",
    });
  });

  it("copies only the part of rest picked, when there is one", async () => {
    const { changed } = renderEditor({
      ...DRAFT,
      groups: [
        {
          name: "",
          rows: [
            { ...EMPTY_ROW, ingredient: "basil", rest: "a handful, torn" },
          ],
        },
      ],
    });
    const first = await edit(1);
    const rest = within(first).getByRole("textbox", { name: "Rest" });
    (rest as HTMLInputElement).setSelectionRange(11, 15);

    await fireEvent.click(
      within(first).getByRole("button", {
        name: "Copy rest of row 1 to preparation",
      }),
    );

    expect(changed()?.groups[0]?.rows[0]?.preparation).toBe("torn");
  });

  // #202: folded, a row's rest is greyed, since none of it is saved.
  it("greys out rest on a folded row", () => {
    renderEditor();

    const line = within(row(1)).getByRole("button", { name: "Edit row 1" });
    expect(within(line).getByText("Juice of")).toHaveClass("quiet");
    expect(within(line).getByText(/2 lemon/)).not.toHaveClass("quiet");
  });

  it("says there are none yet", () => {
    renderEditor({ ...DRAFT, groups: [] });

    expect(screen.getByText(/No ingredients yet/)).toBeVisible();
  });
});

describe("the steps", () => {
  it("shows each step, and edits one", async () => {
    const { changed } = renderEditor();

    await openStep(1);
    expect(screen.getByRole("textbox", { name: "Step 1" })).toHaveValue(
      "Zest the lemons.",
    );
    await openStep(2);
    await fireEvent.input(screen.getByRole("textbox", { name: "Step 2" }), {
      target: { value: "Bake for 30 minutes." },
    });

    expect(changed()?.steps).toEqual([
      DRAFT.steps[0],
      { title: "", text: "Bake for 30 minutes." },
    ]);
  });

  it("deletes a step", async () => {
    const { changed } = renderEditor();
    await openStep(1);

    await fireEvent.click(
      screen.getByRole("button", { name: "Delete step 1" }),
    );

    expect(changed()?.steps).toEqual([DRAFT.steps[1]]);
  });

  it("adds a step below the last", async () => {
    const { changed } = renderEditor();

    await fireEvent.click(
      screen.getByRole("button", { name: "Add a step after step 2" }),
    );

    expect(changed()?.steps).toEqual([...DRAFT.steps, { title: "", text: "" }]);
  });

  it("adds a step after any step", async () => {
    const { changed } = renderEditor();
    await openStep(1);

    await fireEvent.click(
      screen.getByRole("button", { name: "Add a step after step 1" }),
    );

    expect(changed()?.steps).toEqual([
      DRAFT.steps[0],
      { title: "", text: "" },
      DRAFT.steps[1],
    ]);
  });

  it("adds the first step when there are none", async () => {
    const { changed } = renderEditor({ ...DRAFT, steps: [] });

    await fireEvent.click(screen.getByRole("button", { name: "Add a step" }));

    expect(changed()?.steps).toEqual([{ title: "", text: "" }]);
  });

  it("shows each step's title, and edits one", async () => {
    const { changed } = renderEditor();

    await openStep(1);
    expect(screen.getByRole("textbox", { name: "Step 1 title" })).toHaveValue(
      "The lemons",
    );
    await openStep(2);
    await fireEvent.input(
      screen.getByRole("textbox", { name: "Step 2 title" }),
      { target: { value: "Baking" } },
    );

    expect(changed()?.steps[1]).toEqual({ title: "Baking", text: "Bake." });
  });

  // #185: steps fold to one line, as rows do.
  it("shows each step as one line, and opens one to edit", async () => {
    renderEditor();

    expect(screen.queryByRole("textbox", { name: "Step 1" })).toBeNull();
    const line = screen.getByRole("button", { name: "Edit step 1" });
    expect(line).toHaveTextContent("1. The lemons: Zest the lemons.");
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: "Edit step 2" }),
    ).toHaveTextContent("2. Bake.");
    expect(screen.queryByRole("button", { name: "Delete step 1" })).toBeNull();

    await fireEvent.click(line);

    expect(screen.getByRole("textbox", { name: "Step 1" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Delete step 1" })).toBeVisible();
    const fold = screen.getByRole("button", { name: "Fold step 1" });
    expect(fold).toHaveAttribute("aria-expanded", "true");
    await fireEvent.click(fold);
    expect(screen.queryByRole("textbox", { name: "Step 1" })).toBeNull();
  });

  it("calls an empty step empty", () => {
    renderEditor({ ...DRAFT, steps: [{ title: "", text: "" }] });

    expect(
      screen.getByRole("button", { name: "Edit step 1" }),
    ).toHaveTextContent("1. Empty step");
  });

  it("folds an open row when a step opens, one thing at a time", async () => {
    renderEditor();
    await edit(1);

    await openStep(2);

    expect(within(row(1)).queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Step 2" })).toBeVisible();
  });

  it("opens the step it adds", async () => {
    renderLiveEditor();

    await fireEvent.click(
      screen.getByRole("button", { name: "Add a step after step 2" }),
    );

    expect(screen.getByRole("textbox", { name: "Step 3" })).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Step 2" })).toBeNull();
  });

  it("keeps the open step open as it moves", async () => {
    renderLiveEditor();
    await openStep(1);

    await fireEvent.click(
      screen.getByRole("button", { name: "Move step 1 down" }),
    );

    expect(screen.getByRole("textbox", { name: "Step 2" })).toHaveValue(
      "Zest the lemons.",
    );
    expect(screen.queryByRole("textbox", { name: "Step 1" })).toBeNull();
  });
});

describe("what stops a save", () => {
  // A row that stops a save is open, so its mark can be seen.
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
      within(second).getByRole("combobox", { name: "Ingredient" }),
    ).toBeInvalid();
    expect(within(second).getByRole("textbox", { name: "Qty" })).toBeValid();
  });
});

// M9: rows and steps move one place at a time, as on the site's ↑ and ↓.
describe("moving rows and steps", () => {
  it("moves a row down, and up", async () => {
    const { changed } = renderLiveEditor();
    await edit(1);

    await fireEvent.click(
      within(row(1)).getByRole("button", { name: "Move row 1 down" }),
    );
    expect(changed()?.groups[0]?.rows.map((one) => one.quantity)).toEqual([
      "1",
      "2",
    ]);

    await fireEvent.click(
      within(row(2)).getByRole("button", { name: "Move row 2 up" }),
    );
    expect(changed()?.groups[0]).toEqual(DRAFT.groups[0]);
  });

  it("moves a group's last row into the next group, which opens", async () => {
    const { changed } = renderLiveEditor();
    await edit(2);

    await fireEvent.click(
      within(row(2)).getByRole("button", { name: "Move row 2 down" }),
    );

    expect(changed()?.openGroup).toBe(1);
    expect(
      within(row(1, 2)).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveValue("boletus");
  });

  it("cannot move the very first row up, or the very last down", async () => {
    renderEditor(withOpenGroup(DRAFT, 1));
    await edit(1, 2);

    expect(
      within(row(1, 2)).getByRole("button", { name: "Move row 1 down" }),
    ).toBeDisabled();
    expect(
      within(row(1, 2)).getByRole("button", { name: "Move row 1 up" }),
    ).toBeEnabled();
  });

  it("moves a step down, and up", async () => {
    const { changed } = renderLiveEditor();
    await openStep(1);

    await fireEvent.click(
      screen.getByRole("button", { name: "Move step 1 down" }),
    );
    expect(changed()?.steps).toEqual([DRAFT.steps[1], DRAFT.steps[0]]);

    await fireEvent.click(
      screen.getByRole("button", { name: "Move step 2 up" }),
    );
    expect(changed()?.steps).toEqual(DRAFT.steps);
  });

  it("cannot move the first step up, or the last down", async () => {
    renderEditor();

    await openStep(1);
    expect(
      screen.getByRole("button", { name: "Move step 1 up" }),
    ).toBeDisabled();
    await openStep(2);
    expect(
      screen.getByRole("button", { name: "Move step 2 down" }),
    ).toBeDisabled();
  });
});

// M9 (D7): a heading caught inside a group starts a group of its own.
describe("splitting a group", () => {
  it("makes a row the name of a new group holding the rows below it", async () => {
    const { changed } = renderLiveEditor({
      ...DRAFT,
      groups: [
        {
          name: "",
          rows: [
            { ...EMPTY_ROW, quantity: "2", ingredient: "lemon" },
            { ...EMPTY_ROW, rest: "To serve:" },
            { ...EMPTY_ROW, unit: "g", ingredient: "lemon" },
          ],
        },
      ],
    });

    await edit(2);
    await fireEvent.click(
      within(row(2)).getByRole("button", {
        name: "Start a new group named after row 2",
      }),
    );

    expect(changed()?.groups.map((group) => group.name)).toEqual([
      "",
      "To serve",
    ]);
    expect(
      screen.getAllByRole("textbox", { name: "Group name" }).at(-1),
    ).toHaveValue("To serve");
  });
});

// M9 (D12): text too long for its field is named at the field as it is typed.
describe("text too long for its field", () => {
  it("marks the field, and says by how much", () => {
    render(DraftEditor, {
      draft: { ...DRAFT, name: "Lemon tart, the best" },
      vocabulary: {
        ...LISTS,
        limits: { recipe_name: 10, ingredient: 4, step_text: 4 },
      },
      issues: [],
      onChange: vi.fn(),
    });

    const name = screen.getByRole("textbox", { name: "Name" });
    expect(name).toBeInvalid();
    expect(name).toHaveAccessibleDescription(
      "The name is 10 characters too long: it can have 10.",
    );
    expect(
      within(row(1)).getByRole("combobox", { name: "Ingredient" }),
    ).toHaveAccessibleDescription(
      "The ingredient in row 1 of group 1 is 1 character too long: it can have 4.",
    );
    expect(
      screen.getByRole("textbox", { name: "Step 1" }),
    ).toHaveAccessibleDescription(
      "Step 1 is 12 characters too long: it can have 4.",
    );
  });
});
