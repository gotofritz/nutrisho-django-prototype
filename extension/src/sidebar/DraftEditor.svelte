<script lang="ts">
  import { SvelteSet } from "svelte/reactivity";

  import { fitText } from "./fit-text.dom";

  import type { IngredientRow } from "@/core/ingredient-line";
  import {
    addGroup,
    addRow,
    addStep,
    lengthIssues,
    moveRow,
    moveStep,
    removeGroup,
    removeRow,
    removeStep,
    splitGroupAt,
    tagNames,
    tagsText,
    updateGroupName,
    updateRow,
    updateStep,
    withDetails,
    withOpenGroup,
    withTags,
    type DraftIssue,
    type RecipeDraft,
  } from "@/core/recipe-draft";
  import {
    knows,
    knowsCuisine,
    knowsTag,
    type Term,
    type Vocabulary,
  } from "@/core/vocabulary";

  /**
   * The draft's fields, as on the site's recipe editor (plan 012, D5). Every
   * edit goes to `onChange` as a whole new draft; the sidebar keeps it.
   */
  const {
    draft,
    vocabulary,
    issues,
    onChange,
  }: {
    draft: RecipeDraft;
    vocabulary: Vocabulary;
    /** What stopped the last save, each marked at its field. */
    issues: readonly DraftIssue[];
    onChange: (draft: RecipeDraft) => void;
  } = $props();

  type RowField = keyof IngredientRow;

  const ROW_FIELDS: readonly { field: RowField; label: string }[] = [
    { field: "quantity", label: "Quantity" },
    { field: "unit", label: "Unit" },
    { field: "ingredient", label: "Ingredient" },
    { field: "substitute", label: "Substitute" },
    { field: "preparation", label: "Preparation" },
    { field: "note", label: "Note" },
  ];

  /** The list a field's names come from, for the fields that have one. */
  const LISTED: Partial<
    Record<RowField, (lists: Vocabulary) => readonly Term[]>
  > = {
    unit: (lists) => lists.units,
    ingredient: (lists) => lists.ingredients,
    substitute: (lists) => lists.ingredients,
  };

  /** The `<datalist>` that offers a field's names as it is typed in (M8). */
  const SUGGESTED: Partial<Record<RowField, string>> = {
    unit: "unit-names",
    ingredient: "ingredient-names",
    substitute: "ingredient-names",
  };

  const cuisineIsNew = $derived(
    draft.cuisine.trim() !== "" &&
      !knowsCuisine(vocabulary.cuisines, draft.cuisine),
  );

  /** What is too long, by field (D12): flagged as it is typed, not only on a save. */
  const tooLong = $derived(
    lengthIssues(draft, vocabulary.limits).reduce<
      Readonly<Record<string, readonly string[]>>
    >(
      (byField, issue) => ({
        ...byField,
        [issue.field]: [...(byField[issue.field] ?? []), issue.message],
      }),
      {},
    ),
  );

  /** The id of a field's too-long note, when it has one. */
  function longId(field: string): string | undefined {
    return field in tooLong ? `${field.replaceAll(".", "-")}-long` : undefined;
  }

  function describedBy(...ids: (string | undefined)[]): string | undefined {
    const named = ids.filter((id) => id !== undefined);
    return named.length > 0 ? named.join(" ") : undefined;
  }

  function flagged(field: string): boolean {
    return invalid.has(field) || field in tooLong;
  }

  const newTags = $derived(
    tagNames(draft).filter((tag) => !knowsTag(vocabulary.tags, tag)),
  );

  const invalid = $derived(new Set(issues.map((issue) => issue.field)));

  function isNew(field: RowField, value: string): boolean {
    const terms = LISTED[field];
    return (
      terms !== undefined &&
      value.trim() !== "" &&
      !knows(terms(vocabulary), value)
    );
  }

  /** The rows shown as one line, as `group-row`; not kept with the draft. */
  const collapsed = new SvelteSet<string>();

  function toggle(key: string) {
    if (!collapsed.delete(key)) collapsed.add(key);
  }

  /**
   * Keep the collapsed rows on the rows they were, once rows have moved:
   * `place` says where the row at (group, row) is now, or undefined if gone.
   */
  function rekey(
    place: (group: number, row: number) => [number, number] | undefined,
  ) {
    const kept = [...collapsed].flatMap((key) => {
      const [group, row] = key.split("-").map(Number) as [number, number];
      const now = place(group, row);
      return now === undefined ? [] : [`${now[0]}-${now[1]}`];
    });
    collapsed.clear();
    for (const key of kept) collapsed.add(key);
  }

  /** Delete a row; the collapsed rows after it move up with it. */
  function remove(groupIndex: number, rowIndex: number) {
    rekey((group, row) => {
      if (group !== groupIndex || row < rowIndex) return [group, row];
      return row === rowIndex ? undefined : [group, row - 1];
    });
    onChange(removeRow(draft, groupIndex, rowIndex));
  }

  function canMoveRow(groupIndex: number, rowIndex: number, by: -1 | 1) {
    return moveRow(draft, groupIndex, rowIndex, by) !== draft;
  }

  /** ↑ or ↓: within the group, or across into the group before or after. */
  function move(groupIndex: number, rowIndex: number, by: -1 | 1) {
    const rows = draft.groups[groupIndex]?.rows.length ?? 0;
    const to = rowIndex + by;
    if (to >= 0 && to < rows) {
      rekey((group, row) => {
        if (group !== groupIndex) return [group, row];
        if (row === rowIndex) return [group, to];
        return row === to ? [group, rowIndex] : [group, row];
      });
    } else if (by > 0) {
      rekey((group, row) => {
        if (group === groupIndex && row === rowIndex) return [group + 1, 0];
        return group === groupIndex + 1 ? [group, row + 1] : [group, row];
      });
    } else {
      const before = draft.groups[groupIndex - 1]?.rows.length ?? 0;
      rekey((group, row) => {
        if (group !== groupIndex) return [group, row];
        return row === 0 ? [group - 1, before] : [group, row - 1];
      });
    }
    onChange(moveRow(draft, groupIndex, rowIndex, by));
  }

  /** The row names a new group holding the rows below it. */
  function split(groupIndex: number, rowIndex: number) {
    rekey((group, row) => {
      if (group < groupIndex || (group === groupIndex && row < rowIndex)) {
        return [group, row];
      }
      if (group > groupIndex) return [rowIndex === 0 ? group : group + 1, row];
      if (row === rowIndex) return undefined;
      return rowIndex === 0
        ? [group, row - 1]
        : [group + 1, row - rowIndex - 1];
    });
    onChange(splitGroupAt(draft, groupIndex, rowIndex));
  }

  /** One group is open at a time, kept with the draft: ▲ closes it, ▼ opens another. */
  function toggleGroup(groupIndex: number) {
    const open = draft.openGroup === groupIndex ? undefined : groupIndex;
    onChange(withOpenGroup(draft, open));
  }

  /** Delete a group; the collapsed rows of the groups after it move up with them. */
  function removeWholeGroup(groupIndex: number) {
    rekey((group, row) => {
      if (group < groupIndex) return [group, row];
      return group === groupIndex ? undefined : [group - 1, row];
    });
    onChange(removeGroup(draft, groupIndex));
  }

  /** A collapsed group, on one line: `For the syrup · 3 rows`. */
  function groupSummary(group: RecipeDraft["groups"][number]): string {
    const count = group.rows.length;
    const name = group.name.trim() || "Unnamed group";
    return `${name} · ${count} ${count === 1 ? "row" : "rows"}`;
  }

  /** A collapsed row, on one line: `2 lemon · Juice of`. */
  function summary(row: IngredientRow): string {
    const named = [row.quantity, row.unit, row.ingredient]
      .filter((part) => part.trim() !== "")
      .join(" ");
    return [named, row.rest].filter((part) => part.trim() !== "").join(" · ");
  }

  /** Only a whole http(s) address is offered as a link, never `javascript:`. */
  function webAddress(source: string): boolean {
    try {
      const { protocol } = new URL(source.trim());
      return protocol === "http:" || protocol === "https:";
    } catch {
      return false;
    }
  }

  function valueOf(event: Event): string {
    return (event.currentTarget as HTMLInputElement | HTMLTextAreaElement)
      .value;
  }
</script>

{#snippet longNote(field: string)}
  {#if field in tooLong}
    <span class="too-long" id={longId(field)}>{tooLong[field]?.join(" ")}</span>
  {/if}
{/snippet}

<section class="draft" aria-labelledby="draft-heading">
  <h2 id="draft-heading">Recipe</h2>

  <label>
    Name
    <input
      type="text"
      value={draft.name}
      aria-invalid={flagged("name")}
      aria-describedby={longId("name")}
      oninput={(event) =>
        onChange(withDetails(draft, { name: valueOf(event) }))}
    />
  </label>
  {@render longNote("name")}

  <label>
    Servings
    <input
      type="text"
      inputmode="numeric"
      value={draft.servings}
      aria-invalid={invalid.has("servings")}
      oninput={(event) =>
        onChange(withDetails(draft, { servings: valueOf(event) }))}
    />
  </label>

  <label>
    Blurb
    <textarea
      rows="3"
      value={draft.blurb}
      aria-invalid={flagged("blurb")}
      aria-describedby={longId("blurb")}
      oninput={(event) =>
        onChange(withDetails(draft, { blurb: valueOf(event) }))}></textarea>
  </label>
  {@render longNote("blurb")}

  <div class="source">
    <label>
      Source
      <input
        type="url"
        value={draft.source}
        aria-invalid={flagged("source")}
        aria-describedby={longId("source")}
        oninput={(event) =>
          onChange(withDetails(draft, { source: valueOf(event) }))}
      />
    </label>
    {#if webAddress(draft.source)}
      <a
        class="icon"
        href={draft.source}
        target="_blank"
        rel="noreferrer"
        aria-label="Open the source"
        title="Open the source in a new tab">↗</a
      >
    {/if}
  </div>
  {@render longNote("source")}

  <label>
    Cuisine
    <input
      type="text"
      list="cuisine-names"
      value={draft.cuisine}
      aria-invalid={flagged("cuisine")}
      aria-describedby={describedBy(
        cuisineIsNew ? "cuisine-new" : undefined,
        longId("cuisine"),
      )}
      oninput={(event) =>
        onChange(withDetails(draft, { cuisine: valueOf(event) }))}
    />
  </label>
  {#if cuisineIsNew}
    <span class="new" id="cuisine-new"
      >new<span class="hidden">: saving makes it one of your own</span></span
    >
  {/if}
  {@render longNote("cuisine")}

  <label>
    Tags
    <input
      type="text"
      value={tagsText(draft)}
      aria-invalid={flagged("tags")}
      aria-describedby={describedBy(
        newTags.length > 0 ? "tags-new" : undefined,
        longId("tags"),
      )}
      oninput={(event) => onChange(withTags(draft, valueOf(event)))}
    />
  </label>
  {#if newTags.length > 0}
    <span class="new" id="tags-new"
      >new: {newTags.join(", ")}<span class="hidden"
        >: saving makes them your own</span
      ></span
    >
  {/if}
  {@render longNote("tags")}

  <datalist id="cuisine-names">
    {#each vocabulary.cuisines as path (path)}
      <option value={path}></option>
    {/each}
  </datalist>
  <datalist id="ingredient-names">
    {#each vocabulary.ingredients as term (term.name)}
      <option value={term.name}></option>
    {/each}
  </datalist>
  <datalist id="unit-names">
    {#each vocabulary.units as term (term.name)}
      <option value={term.name}></option>
    {/each}
  </datalist>

  <h3>Ingredients</h3>
  {#if draft.groups.length === 0}
    <p class="quiet">
      No ingredients yet: clip them as an ingredient group, or add a group with
      +.
    </p>
  {/if}
  {#each draft.groups as group, groupIndex (groupIndex)}
    {@const groupShut = draft.openGroup !== groupIndex}
    <section class="group" aria-label="Group {groupIndex + 1}">
      <div class="group-head">
        {#if groupShut}
          <p class="summary">{groupSummary(group)}</p>
        {:else}
          <label>
            Group name
            <input
              type="text"
              value={group.name}
              aria-invalid={flagged(`groups.${groupIndex}.name`)}
              aria-describedby={longId(`groups.${groupIndex}.name`)}
              oninput={(event) =>
                onChange(updateGroupName(draft, groupIndex, valueOf(event)))}
            />
          </label>
        {/if}
        <div class="group-tools">
          <button
            type="button"
            class="icon"
            aria-label="Collapse group {groupIndex + 1}"
            aria-expanded={!groupShut}
            onclick={() => toggleGroup(groupIndex)}
            >{groupShut ? "▼" : "▲"}</button
          >
          <button
            type="button"
            class="icon"
            aria-label="Delete group {groupIndex + 1}"
            onclick={() => removeWholeGroup(groupIndex)}>×</button
          >
        </div>
      </div>
      {#if !groupShut}
        {@render longNote(`groups.${groupIndex}.name`)}
      {/if}
      {#each groupShut ? [] : group.rows as row, index (index)}
        {@const key = `${groupIndex}-${index}`}
        {@const shut = collapsed.has(key)}
        <fieldset class="row">
          <legend>Row {index + 1}</legend>
          <div class="tools">
            <button
              type="button"
              class="icon"
              aria-label="Move row {index + 1} up"
              title="Move up"
              disabled={!canMoveRow(groupIndex, index, -1)}
              onclick={() => move(groupIndex, index, -1)}>↑</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Move row {index + 1} down"
              title="Move down"
              disabled={!canMoveRow(groupIndex, index, 1)}
              onclick={() => move(groupIndex, index, 1)}>↓</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Start a new group named after row {index + 1}"
              title="Start a new group named after this row"
              onclick={() => split(groupIndex, index)}>¶</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Collapse row {index + 1}"
              aria-expanded={!shut}
              onclick={() => toggle(key)}>{shut ? "▼" : "▲"}</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Delete row {index + 1}"
              onclick={() => remove(groupIndex, index)}>×</button
            >
          </div>
          {#if shut}
            <p class="summary">{summary(row)}</p>
          {/if}
          {#each shut ? [] : ROW_FIELDS as { field, label } (field)}
            {@const mark = `group-${groupIndex}-row-${index}-${field}-new`}
            {@const at = `groups.${groupIndex}.rows.${index}.${field}`}
            <label>
              {label}
              <input
                type="text"
                list={SUGGESTED[field]}
                value={row[field]}
                aria-invalid={flagged(at)}
                aria-describedby={describedBy(
                  isNew(field, row[field]) ? mark : undefined,
                  longId(at),
                )}
                oninput={(event) =>
                  onChange(
                    updateRow(draft, groupIndex, index, {
                      [field]: valueOf(event),
                    }),
                  )}
              />
            </label>
            {#if isNew(field, row[field])}
              <span class="new" id={mark}
                >new<span class="hidden">: saving makes it one of your own</span
                ></span
              >
            {/if}
            {@render longNote(at)}
          {/each}
          {#if !shut}
            {@const restNote = `group-${groupIndex}-row-${index}-rest-note`}
            <!-- Rest is the row's scratch pad: what is wanted is moved out of it. -->
            <div class="rest">
              <label>
                Rest
                <input
                  type="text"
                  class="scratch"
                  value={row.rest}
                  aria-describedby={restNote}
                  oninput={(event) =>
                    onChange(
                      updateRow(draft, groupIndex, index, {
                        rest: valueOf(event),
                      }),
                    )}
                />
              </label>
              <button
                type="button"
                class="icon"
                aria-label="Clear rest of row {index + 1}"
                onclick={() =>
                  onChange(updateRow(draft, groupIndex, index, { rest: "" }))}
                >🗑</button
              >
            </div>
            <span class="not-saved" id={restNote}>Not saved</span>
          {/if}
        </fieldset>
      {/each}
      {#if !groupShut}
        <button
          type="button"
          class="icon add"
          aria-label="Add an ingredient to group {groupIndex + 1}"
          title="Add an ingredient to group {groupIndex + 1}"
          onclick={() => onChange(addRow(draft, groupIndex))}>+</button
        >
      {/if}
    </section>
  {/each}
  <button
    type="button"
    class="icon add"
    aria-label="Add an ingredient group"
    title="Add an ingredient group"
    onclick={() => onChange(addGroup(draft))}>+</button
  >

  <h3>Steps</h3>
  {#if draft.steps.length === 0}
    <p class="quiet">No steps yet: clip them, or add one with +.</p>
  {/if}
  <ol class="steps">
    {#each draft.steps as step, index (index)}
      <li>
        <div class="step-head">
          <input
            type="text"
            placeholder="Step {index + 1} title"
            aria-label="Step {index + 1} title"
            value={step.title}
            aria-invalid={flagged(`steps.${index}.title`)}
            aria-describedby={longId(`steps.${index}.title`)}
            oninput={(event) =>
              onChange(updateStep(draft, index, { title: valueOf(event) }))}
          />
          <button
            type="button"
            class="icon"
            aria-label="Move step {index + 1} up"
            title="Move up"
            disabled={index === 0}
            onclick={() => onChange(moveStep(draft, index, -1))}>↑</button
          >
          <button
            type="button"
            class="icon"
            aria-label="Move step {index + 1} down"
            title="Move down"
            disabled={index === draft.steps.length - 1}
            onclick={() => onChange(moveStep(draft, index, 1))}>↓</button
          >
          <button
            type="button"
            class="icon"
            aria-label="Delete step {index + 1}"
            onclick={() => onChange(removeStep(draft, index))}>×</button
          >
        </div>
        {@render longNote(`steps.${index}.title`)}
        <textarea
          class="step-text"
          rows="2"
          aria-label="Step {index + 1}"
          use:fitText={step.text}
          value={step.text}
          aria-invalid={flagged(`steps.${index}.text`)}
          aria-describedby={longId(`steps.${index}.text`)}
          oninput={(event) =>
            onChange(updateStep(draft, index, { text: valueOf(event) }))}
        ></textarea>
        {@render longNote(`steps.${index}.text`)}
        <button
          type="button"
          class="icon add"
          aria-label="Add a step after step {index + 1}"
          title="Add a step after step {index + 1}"
          onclick={() => onChange(addStep(draft, index))}>+</button
        >
      </li>
    {/each}
  </ol>
  {#if draft.steps.length === 0}
    <button
      type="button"
      class="icon add"
      aria-label="Add a step"
      title="Add a step"
      onclick={() => onChange(addStep(draft))}>+</button
    >
  {/if}
</section>

<style>
  .draft,
  .group,
  .row {
    display: grid;
    gap: 0.5rem;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h3 {
    font-size: 0.9375rem;
  }

  label {
    display: grid;
    gap: 0.125rem;
    font-size: 0.875rem;
  }

  input,
  textarea {
    font: inherit;
  }

  .row {
    position: relative;
    grid-template-columns: 1fr;
    border: 1px solid GrayText;
    border-radius: 0.25rem;
    padding: 0.5rem;
  }

  /* On the row's top border, opposite its legend. */
  .tools {
    position: absolute;
    top: -0.875rem;
    right: 0.5rem;
    display: flex;
    gap: 0.25rem;
    background: Canvas;
  }

  .group {
    padding-left: 0.5rem;
    border-left: 3px solid GrayText;
  }

  .group-head {
    display: flex;
    align-items: end;
    gap: 0.5rem;
  }

  .group-head > :first-child {
    flex: 1;
  }

  .group-tools {
    display: flex;
    gap: 0.25rem;
  }

  .icon {
    min-width: 1.5rem;
    padding: 0 0.25rem;
    font-size: 0.75rem;
    line-height: 1.5;
  }

  .rest {
    display: flex;
    align-items: end;
    gap: 0.25rem;
  }

  .rest > label {
    flex: 1;
  }

  /* A scratch pad: dashed and shaded, since none of it is saved. */
  .scratch {
    border: 1px dashed GrayText;
    background: color-mix(in srgb, GrayText 12%, Canvas);
    font-style: italic;
  }

  .not-saved {
    margin-top: -0.375rem;
    color: GrayText;
    font-size: 0.75rem;
  }

  .step-head {
    display: flex;
    gap: 0.25rem;
  }

  .step-head > input {
    flex: 1;
  }

  .source {
    display: flex;
    align-items: end;
    gap: 0.25rem;
  }

  .source > label {
    flex: 1;
  }

  .source a {
    text-decoration: none;
  }

  .add {
    justify-self: start;
    font-size: 1rem;
  }

  .summary {
    font-size: 0.875rem;
  }

  .steps li {
    display: grid;
    gap: 0.25rem;
  }

  .new {
    justify-self: start;
    margin-top: -0.25rem;
    padding: 0 0.375rem;
    border-radius: 0.25rem;
    background: #fff3c4;
    color: #5c4400;
    font-size: 0.75rem;
  }

  /* Numbered by each title's placeholder, so the list needs no indent. */
  .steps {
    display: grid;
    gap: 0.75rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* As tall as its text (fitText), so a clipped step shows whole. */
  .step-text {
    box-sizing: border-box;
    overflow: hidden;
    resize: none;
  }

  .too-long {
    margin-top: -0.25rem;
    color: #a40e26;
    font-size: 0.75rem;
  }

  .quiet {
    color: GrayText;
    font-size: 0.875rem;
  }

  [aria-invalid="true"] {
    outline: 2px solid #a40e26;
  }

  .hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
