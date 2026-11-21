<script lang="ts">
  import type { IngredientRow } from "@/core/ingredient-line";
  import {
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
    <section class="group" aria-label="Group {groupIndex + 1}">
      <label>
        Group name
        <input
          type="text"
          value={group.name}
          oninput={(event) =>
            onChange(updateGroupName(draft, groupIndex, valueOf(event)))}
        />
      </label>
      {#each group.rows as row, index (index)}
        <fieldset class="row">
          <legend>Row {index + 1}</legend>
          {#each ROW_FIELDS as { field, label } (field)}
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
        <textarea
          rows="2"
          aria-label="Step {index + 1}"
          value={step}
          oninput={(event) =>
            onChange(updateStep(draft, index, valueOf(event)))}></textarea>
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
    grid-template-columns: 1fr;
    border: 1px solid GrayText;
    border-radius: 0.25rem;
    padding: 0.5rem;
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
