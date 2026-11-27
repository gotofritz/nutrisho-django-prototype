<script lang="ts">
  import type { Snippet } from "svelte";
  import { SvelteSet } from "svelte/reactivity";

  import AskButton from "./AskButton.svelte";
  import { fitText } from "./fit-text.dom";

  import type { IngredientRow } from "@/core/ingredient-line";
  import { lineOf } from "@/core/model-answer";
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
    onAskModel,
    onAskModelSteps,
    onAskModelBlurb,
    otherModels = [],
    defaultModel,
    holdMs,
    asking = false,
    modelAt,
    modelFeedback,
  }: {
    draft: RecipeDraft;
    vocabulary: Vocabulary;
    /** What stopped the last save, each marked at its field. */
    issues: readonly DraftIssue[];
    onChange: (draft: RecipeDraft) => void;
    /** Send a group's lines to the user's own model (M13); absent while none is set up. */
    onAskModel?: (groupIndex: number, setupId?: string) => void;
    /** Ask the user's own model to rewrite the steps; none while it is off. */
    onAskModelSteps?: (setupId?: string) => void;
    /** Ask the user's own model to rewrite the blurb (#205); none while it is off. */
    onAskModelBlurb?: (setupId?: string) => void;
    /** The set-ups other than the default, to ask one once (#183). */
    otherModels?: readonly { readonly id: string; readonly name: string }[];
    /** The default set-up's name, which heads that menu, faded. */
    defaultModel?: string;
    /** How long *Ask the model* is held to open that menu. */
    holdMs?: number;
    /** A model is working on a group, so no other is asked meanwhile. */
    asking?: boolean;
    /** The group, the steps or the blurb the model was last asked about. */
    modelAt?: number | "steps" | "blurb";
    /** What the model is doing or did, shown beside the button pressed. */
    modelFeedback?: Snippet;
  } = $props();

  type RowField = keyof IngredientRow;

  const ROW_FIELDS: readonly { field: RowField; label: string }[] = [
    { field: "quantity", label: "Qty" },
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

  /**
   * The one thing open for editing (#184, #185): a row as `group-row`, a
   * step as `step-N`, or the details. Everything else reads as one line.
   * One at a time across the draft, and not kept with it.
   */
  const opened = new SvelteSet<string>();
  const DETAILS = "details";
  const ROW_KEY = /^\d+-\d+$/;

  function stepKey(index: number): string {
    return `step-${index}`;
  }

  /** The fields under the name that fold with it, by issue field. */
  const DETAIL_FIELDS = ["servings", "blurb", "source", "cuisine", "tags"];

  /** Details that stop a save, or are too long, stay open. */
  const detailsShut = $derived(
    !opened.has(DETAILS) &&
      ![...invalid, ...Object.keys(tooLong)].some((field) =>
        DETAIL_FIELDS.includes(field),
      ),
  );

  /** The folded details, on one line: `Serves 4 · med.italy · dinner · example.test`. */
  const detailsLine = $derived(
    [
      draft.servings.trim() === "" ? "" : `Serves ${draft.servings.trim()}`,
      draft.cuisine.trim(),
      tagNames(draft).join(", "),
      hostOf(draft.source),
    ]
      .filter((part) => part !== "")
      .join(" · "),
  );

  /** A source by its site's name, or as typed when it is no address. */
  function hostOf(source: string): string {
    try {
      return new URL(source.trim()).hostname || source.trim();
    } catch {
      return source.trim();
    }
  }

  /** A step with a field that stops a save, or is too long, stays open. */
  function stepNeedsLooking(index: number): boolean {
    const at = `steps.${index}.`;
    return [...invalid, ...Object.keys(tooLong)].some((field) =>
      field.startsWith(at),
    );
  }

  /** A folded step, on one line: `The lemons: Zest the lemons.` */
  function stepLine(step: RecipeDraft["steps"][number]): string {
    return (
      [step.title, step.text]
        .map((part) => part.trim())
        .filter((part) => part !== "")
        .join(": ") || "Empty step"
    );
  }

  /** Keep the open step on the step it was: `place` says where it is now. */
  function rekeySteps(place: (index: number) => number | undefined) {
    const kept = [...opened].flatMap((key) => {
      if (!key.startsWith("step-")) return [key];
      const now = place(Number(key.slice("step-".length)));
      return now === undefined ? [] : [stepKey(now)];
    });
    opened.clear();
    for (const key of kept) opened.add(key);
  }

  /** Add a step after another, or the first, open to type into. */
  function addStepAfter(index?: number) {
    opened.clear();
    opened.add(stepKey(index === undefined ? 0 : index + 1));
    onChange(addStep(draft, index));
  }

  function removeStepAt(index: number) {
    rekeySteps((at) => {
      if (at < index) return at;
      return at === index ? undefined : at - 1;
    });
    onChange(removeStep(draft, index));
  }

  function moveStepBy(index: number, by: -1 | 1) {
    rekeySteps((at) => {
      if (at === index) return index + by;
      return at === index + by ? index : at;
    });
    onChange(moveStep(draft, index, by));
  }

  function toggle(key: string) {
    const wasOpen = opened.has(key);
    opened.clear();
    if (!wasOpen) opened.add(key);
  }

  /** A row with a field that stops a save, or is too long, stays open. */
  function needsLooking(groupIndex: number, rowIndex: number): boolean {
    const at = `groups.${groupIndex}.rows.${rowIndex}.`;
    return [...invalid, ...Object.keys(tooLong)].some((field) =>
      field.startsWith(at),
    );
  }

  /** Add an ingredient at the end of a group, open to type into. */
  function addIngredient(groupIndex: number) {
    opened.clear();
    opened.add(`${groupIndex}-${draft.groups[groupIndex]?.rows.length ?? 0}`);
    onChange(addRow(draft, groupIndex));
  }

  /**
   * Keep the open row on the row it was, once rows have moved:
   * `place` says where the row at (group, row) is now, or undefined if gone.
   */
  function rekey(
    place: (group: number, row: number) => [number, number] | undefined,
  ) {
    const kept = [...opened].flatMap((key) => {
      if (!ROW_KEY.test(key)) return [key];
      const [group, row] = key.split("-").map(Number) as [number, number];
      const now = place(group, row);
      return now === undefined ? [] : [`${now[0]}-${now[1]}`];
    });
    opened.clear();
    for (const key of kept) opened.add(key);
  }

  /** Delete a row; an open row after it moves up with it. */
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

  /** Delete a group; an open row in a group after it moves up with it. */
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

  /** A folded row, on one line as a recipe prints it: `2 lemon · Juice of`. */
  function summary(row: IngredientRow): string {
    const named = lineOf({ ...row, rest: "" });
    return [named, row.rest].filter((part) => part.trim() !== "").join(" · ");
  }

  /** Whether a folded row holds a name the lists do not, to say so on its line. */
  function holdsNew(row: IngredientRow): boolean {
    return ROW_FIELDS.some(({ field }) => isNew(field, row[field]));
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
    <span class="hidden">Name</span>
    <input
      type="text"
      class="recipe-name"
      placeholder="Name"
      value={draft.name}
      aria-invalid={flagged("name")}
      aria-describedby={longId("name")}
      oninput={(event) =>
        onChange(withDetails(draft, { name: valueOf(event) }))}
    />
  </label>
  {@render longNote("name")}

  {#if detailsShut}
    <!-- Folded as a recipe's byline reads (#185): servings, cuisine, tags
         and source on one line, and the blurb beneath. -->
    <button
      type="button"
      class="line details-line"
      aria-label="Edit the details"
      aria-expanded="false"
      onclick={() => toggle(DETAILS)}
      ><span
        ><span class:quiet={detailsLine === ""}
          >{detailsLine || "No servings, cuisine or tags yet"}</span
        >{#if cuisineIsNew || newTags.length > 0}&nbsp;<span class="new"
            >new</span
          >{/if}</span
      >{#if draft.blurb.trim() !== ""}
        <span class="blurb">{draft.blurb}</span>{/if}</button
    >
  {:else}
    <div class="details open">
      <div class="tools">
        <button
          type="button"
          class="icon"
          aria-label="Fold the details"
          title="Fold"
          aria-expanded="true"
          onclick={() => toggle(DETAILS)}>▲</button
        >
      </div>
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
      {#if onAskModelBlurb !== undefined && draft.blurb.trim() !== ""}
        <div class="blurb-ask">
          <AskButton
            label="Ask the model about the blurb"
            others={otherModels}
            current={defaultModel}
            {holdMs}
            disabled={asking}
            onAsk={(setupId) => onAskModelBlurb(setupId)}
          />
        </div>
      {/if}
      {#if modelAt === "blurb"}
        {@render modelFeedback?.()}
      {/if}

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
          >new<span class="hidden">: saving makes it one of your own</span
          ></span
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
    </div>
  {/if}

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

  <h3 class="part">Ingredients</h3>
  {#if draft.groups.length === 0}
    <p class="quiet">
      No ingredients yet: clip them as an ingredient group, or add a group.
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
          {#if onAskModel !== undefined && !groupShut}
            <AskButton
              label="Ask the model about group {groupIndex + 1}"
              others={otherModels}
              current={defaultModel}
              {holdMs}
              disabled={asking}
              onAsk={(setupId) => onAskModel(groupIndex, setupId)}
            />
          {/if}
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
      {#if modelAt === groupIndex}
        {@render modelFeedback?.()}
      {/if}
      {#each groupShut ? [] : group.rows as row, index (index)}
        {@const key = `${groupIndex}-${index}`}
        {@const shut = !opened.has(key) && !needsLooking(groupIndex, index)}
        <fieldset class="row" class:open={!shut}>
          <legend class="hidden">Row {index + 1}</legend>
          {#if shut}
            <button
              type="button"
              class="line"
              aria-label="Edit row {index + 1}"
              aria-expanded="false"
              onclick={() => toggle(key)}
              ><span class:quiet={summary(row) === ""}
                >{summary(row) || "Empty row"}</span
              >{#if holdsNew(row)}
                <span class="new">new</span>{/if}</button
            >
          {:else}
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
                aria-label="Delete row {index + 1}"
                title="Delete"
                onclick={() => remove(groupIndex, index)}>×</button
              >
              <button
                type="button"
                class="icon"
                aria-label="Fold row {index + 1}"
                title="Fold"
                aria-expanded="true"
                onclick={() => toggle(key)}>▲</button
              >
            </div>
          {/if}
          {#if !shut}
            {@const restNote = `group-${groupIndex}-row-${index}-rest-note`}
            {@const label = (field: RowField) =>
              ROW_FIELDS.find((each) => each.field === field)?.label ?? field}
            <!-- As a recipe says it: quantity, unit and ingredient on one
                 line; preparation and note beneath quantity and unit, with
                 substitute and rest beneath the ingredient. -->
            <div class="fields">
              {#each ["quantity", "unit", "ingredient"] as const as field (field)}
                <div class="cell">
                  {@render rowField(
                    groupIndex,
                    index,
                    row,
                    field,
                    label(field),
                  )}
                </div>
              {/each}
              <div class="cell wide">
                {@render rowField(
                  groupIndex,
                  index,
                  row,
                  "preparation",
                  label("preparation"),
                )}
              </div>
              <div class="cell">
                {@render rowField(
                  groupIndex,
                  index,
                  row,
                  "substitute",
                  label("substitute"),
                )}
              </div>
              <div class="cell wide">
                {@render rowField(
                  groupIndex,
                  index,
                  row,
                  "note",
                  label("note"),
                )}
              </div>
              <!-- Rest is the row's scratch pad: what is wanted is moved out of it. -->
              <div class="cell">
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
                      onChange(
                        updateRow(draft, groupIndex, index, { rest: "" }),
                      )}>🗑</button
                  >
                </div>
                <span class="not-saved" id={restNote}>Not saved</span>
              </div>
            </div>
          {/if}
        </fieldset>
      {/each}
      {#if !groupShut}
        <button
          type="button"
          class="add"
          aria-label="Add an ingredient to group {groupIndex + 1}"
          onclick={() => addIngredient(groupIndex)}>+ ingredient</button
        >
      {/if}
    </section>
  {/each}
  <button
    type="button"
    class="add"
    aria-label="Add an ingredient group"
    onclick={() => onChange(addGroup(draft))}>+ group</button
  >

  <div class="steps-head part">
    <h3>Steps</h3>
    {#if onAskModelSteps !== undefined && draft.steps.length > 0}
      <AskButton
        label="Ask the model about the steps"
        others={otherModels}
        current={defaultModel}
        {holdMs}
        disabled={asking}
        onAsk={(setupId) => onAskModelSteps(setupId)}
      />
    {/if}
  </div>
  {#if modelAt === "steps"}
    {@render modelFeedback?.()}
  {/if}
  {#if draft.steps.length === 0}
    <p class="quiet">No steps yet: clip them, or add one.</p>
  {/if}
  <ol class="steps">
    {#each draft.steps as step, index (index)}
      {@const shut = !opened.has(stepKey(index)) && !stepNeedsLooking(index)}
      <li class:open={!shut}>
        {#if shut}
          <button
            type="button"
            class="line"
            aria-label="Edit step {index + 1}"
            aria-expanded="false"
            onclick={() => toggle(stepKey(index))}
            ><span class="step-line"
              >{index + 1}.
              <span class:quiet={stepLine(step) === "Empty step"}
                >{stepLine(step)}</span
              ></span
            ></button
          >
        {:else}
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
              onclick={() => moveStepBy(index, -1)}>↑</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Move step {index + 1} down"
              title="Move down"
              disabled={index === draft.steps.length - 1}
              onclick={() => moveStepBy(index, 1)}>↓</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Delete step {index + 1}"
              title="Delete"
              onclick={() => removeStepAt(index)}>×</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Fold step {index + 1}"
              title="Fold"
              aria-expanded="true"
              onclick={() => toggle(stepKey(index))}>▲</button
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
          {#if index < draft.steps.length - 1}
            <button
              type="button"
              class="add"
              aria-label="Add a step after step {index + 1}"
              onclick={() => addStepAfter(index)}>+ step</button
            >
          {/if}
        {/if}
      </li>
    {/each}
  </ol>
  {#if draft.steps.length === 0}
    <button
      type="button"
      class="add"
      aria-label="Add a step"
      onclick={() => addStepAfter()}>+ step</button
    >
  {:else}
    <button
      type="button"
      class="add"
      aria-label="Add a step after step {draft.steps.length}"
      onclick={() => addStepAfter(draft.steps.length - 1)}>+ step</button
    >
  {/if}
</section>

{#snippet rowField(
  groupIndex: number,
  index: number,
  row: IngredientRow,
  field: RowField,
  label: string,
)}
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
      >new<span class="hidden">: saving makes it one of your own</span></span
    >
  {/if}
  {@render longNote(at)}
{/snippet}

<style>
  /* The site's look is global (styles/clipper.css); this is layout only. */
  .draft,
  .group,
  .row {
    display: grid;
    gap: 0.5rem;
  }

  .draft {
    gap: 1rem;
  }

  label {
    display: grid;
    gap: 0.125rem;
    font-size: 0.875rem;
  }

  /* A part opens with room above its dotted line. */
  .part {
    margin-top: 1rem;
  }

  /* Rows sit flush, ruled apart (clipper.css); the open one has room inside. */
  .row {
    grid-template-columns: 1fr;
    gap: 0.25rem;
  }

  .row.open {
    padding: 0.25rem 0.5rem 0.75rem;
  }

  .line {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
    justify-content: space-between;
    width: 100%;
    padding: 0.375rem 0.5rem;
  }

  .fields {
    display: grid;
    /* Qty and unit narrow; the ingredient, substitute and rest take the rest. */
    grid-template-columns: 3rem 5rem minmax(0, 1fr);
    gap: 0.5rem;
    align-items: start;
  }

  .cell {
    display: grid;
    gap: 0.125rem;
    min-width: 0;
  }

  .cell.wide {
    grid-column: span 2;
  }

  .cell input {
    width: 100%;
    min-width: 0;
  }

  .tools {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0;
  }

  /* A group's rows hang from its bar (clipper.css), with its name above. */
  .group {
    gap: 0;
    padding-left: 0.5rem;
  }

  .group-head {
    margin-bottom: 0.25rem;
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
  }

  .icon {
    min-width: 1.75rem;
    padding: 0.25rem;
    font-size: 0.875rem;
    line-height: 1.25;
  }

  .rest {
    display: flex;
    align-items: end;
    gap: 0.25rem;
  }

  .rest > label {
    flex: 1;
  }

  /* A scratch pad: pencil, italic and a dashed line, since none of it is saved. */
  .scratch {
    border-bottom-style: dashed;
    color: var(--pencil);
    font-style: italic;
  }

  .not-saved {
    color: var(--pencil);
    font-size: 0.75rem;
    font-style: italic;
  }

  .step-head {
    display: flex;
    align-items: end;
    gap: 0;
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
    padding: 0.25rem 0.5rem;
  }

  .summary {
    color: var(--pencil);
    font-size: 0.875rem;
  }

  .steps li {
    display: grid;
    gap: 0.25rem;
  }

  .steps li.open,
  .details {
    padding: 0.25rem 0.5rem 0.75rem;
  }

  .details {
    display: grid;
    position: relative;
    gap: 0.75rem;
  }

  /* ▲ sits in the corner, beside the first label, not on a line of its own. */
  .details > .tools {
    position: absolute;
    top: 0.25rem;
    right: 0.25rem;
  }

  .details-line {
    display: grid;
    gap: 0.25rem;
    justify-content: stretch;
  }

  /* A folded step or blurb shows its start, not all of it. */
  .step-line,
  .blurb {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  .blurb {
    -webkit-line-clamp: 3;
    line-clamp: 3;
  }

  .new {
    justify-self: start;
    margin-top: -0.25rem;
  }

  /* Under the blurb, at its end, as the steps' button sits by their heading. */
  .blurb-ask {
    display: flex;
    justify-content: flex-end;
  }

  /* Numbered by each title's placeholder, so the list needs no indent. */
  .steps-head {
    display: flex;
    margin-top: 1rem;
    gap: 0.5rem;
    align-items: baseline;
    justify-content: space-between;
  }

  .steps {
    display: grid;
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* As tall as its text (fitText), so a clipped step shows whole. */
  .step-text {
    overflow: hidden;
    resize: none;
  }

  .too-long {
    margin-top: -0.25rem;
    color: var(--smock-red);
    font-size: 0.75rem;
    font-style: italic;
  }
</style>
