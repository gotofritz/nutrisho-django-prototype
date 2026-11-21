<script lang="ts">
  import { SvelteSet } from "svelte/reactivity";

  import type { IngredientRow } from "@/core/ingredient-line";
  import {
    removeGroup,
    removeRow,
    updateGroupName,
    updateRow,
    updateStep,
    withDetails,
    type DraftIssue,
    type RecipeDraft,
  } from "@/core/recipe-draft";
  import { knows, type Term, type Vocabulary } from "@/core/vocabulary";

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
    { field: "rest", label: "Rest" },
  ];

  /** The list a field's names come from, for the fields that have one. */
  const LISTED: Partial<
    Record<RowField, (lists: Vocabulary) => readonly Term[]>
  > = {
    unit: (lists) => lists.units,
    ingredient: (lists) => lists.ingredients,
  };

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

  /** Delete a row; the collapsed rows after it move up with it. */
  function remove(groupIndex: number, rowIndex: number) {
    const kept = [...collapsed].flatMap((key) => {
      const [group, row] = key.split("-").map(Number) as [number, number];
      if (group !== groupIndex || row < rowIndex) return [key];
      return row === rowIndex ? [] : [`${group}-${row - 1}`];
    });
    collapsed.clear();
    for (const key of kept) collapsed.add(key);
    onChange(removeRow(draft, groupIndex, rowIndex));
  }

  /** The groups shown as one line, by index; not kept with the draft. */
  const shutGroups = new SvelteSet<number>();

  function toggleGroup(groupIndex: number) {
    if (!shutGroups.delete(groupIndex)) shutGroups.add(groupIndex);
  }

  /** Delete a group; the collapsed groups and rows after it move up with it. */
  function removeWholeGroup(groupIndex: number) {
    const groups = [...shutGroups].flatMap((at) =>
      at < groupIndex ? [at] : at === groupIndex ? [] : [at - 1],
    );
    shutGroups.clear();
    for (const at of groups) shutGroups.add(at);

    const rows = [...collapsed].flatMap((key) => {
      const [group, row] = key.split("-").map(Number) as [number, number];
      if (group < groupIndex) return [key];
      return group === groupIndex ? [] : [`${group - 1}-${row}`];
    });
    collapsed.clear();
    for (const key of rows) collapsed.add(key);

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

  function valueOf(event: Event): string {
    return (event.currentTarget as HTMLInputElement | HTMLTextAreaElement)
      .value;
  }
</script>

<section class="draft" aria-labelledby="draft-heading">
  <h2 id="draft-heading">Recipe</h2>

  <label>
    Name
    <input
      type="text"
      value={draft.name}
      aria-invalid={invalid.has("name")}
      oninput={(event) =>
        onChange(withDetails(draft, { name: valueOf(event) }))}
    />
  </label>

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
      oninput={(event) =>
        onChange(withDetails(draft, { blurb: valueOf(event) }))}></textarea>
  </label>

  <label>
    Source
    <input
      type="url"
      value={draft.source}
      oninput={(event) =>
        onChange(withDetails(draft, { source: valueOf(event) }))}
    />
  </label>

  <h3>Ingredients</h3>
  {#if draft.groups.length === 0}
    <p class="quiet">
      No ingredients yet: clip them as an ingredient group, or send lines from
      the clipboard.
    </p>
  {/if}
  {#each draft.groups as group, groupIndex (groupIndex)}
    {@const groupShut = shutGroups.has(groupIndex)}
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
      {#each groupShut ? [] : group.rows as row, index (index)}
        {@const key = `${groupIndex}-${index}`}
        {@const shut = collapsed.has(key)}
        <fieldset class="row">
          <legend>Row {index + 1}</legend>
          <div class="tools">
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
            <label>
              {label}
              <input
                type="text"
                value={row[field]}
                aria-invalid={invalid.has(
                  `groups.${groupIndex}.rows.${index}.${field}`,
                )}
                aria-describedby={isNew(field, row[field]) ? mark : undefined}
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
          {/each}
        </fieldset>
      {/each}
    </section>
  {/each}

  <h3>Steps</h3>
  {#if draft.steps.length === 0}
    <p class="quiet">No steps yet: send lines to them from the clipboard.</p>
  {/if}
  <ol class="steps">
    {#each draft.steps as step, index (index)}
      <li>
        <input
          type="text"
          placeholder="Title"
          aria-label="Step {index + 1} title"
          value={step.title}
          oninput={(event) =>
            onChange(updateStep(draft, index, { title: valueOf(event) }))}
        />
        <textarea
          rows="2"
          aria-label="Step {index + 1}"
          value={step.text}
          oninput={(event) =>
            onChange(updateStep(draft, index, { text: valueOf(event) }))}
        ></textarea>
      </li>
    {/each}
  </ol>
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

  .steps {
    display: grid;
    gap: 0.5rem;
    margin: 0;
    padding-left: 1.25rem;
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
