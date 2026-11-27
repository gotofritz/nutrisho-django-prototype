<script lang="ts">
  import { untrack } from "svelte";

  import type { Clipping } from "@/core/clipping";
  import {
    EMPTY_DRAFTS,
    afterClip,
    choose,
    currentDraft,
    discard,
    markSaved,
    withDraft,
    type Drafts,
  } from "@/core/drafts";
  import { describeSplit, lineOf, readModelAnswer } from "@/core/model-answer";
  import {
    HOLD_MS,
    chosenSetup,
    holdOf,
    type ModelSetup,
  } from "@/core/model-settings";
  import { describeBlurb, readBlurbAnswer } from "@/core/model-blurb";
  import { describeSteps, readStepsAnswer } from "@/core/model-steps";
  import type {
    ClippingStore,
    DraftStore,
    LineModel,
    ModelSettingsStore,
    NutrishoClient,
    NutrishoError,
    SettingsStore,
    StoreError,
  } from "@/core/ports/types";
  import {
    checkDraft,
    explainRefusal,
    type DraftIssue,
    withDetails,
    withGroupRows,
    withSteps,
    withOpenGroup,
    type RecipeDraft,
  } from "@/core/recipe-draft";
  import type { Result } from "@/core/result";
  import { EMPTY_VOCABULARY, knows, type Vocabulary } from "@/core/vocabulary";
  import type { LogEntry } from "@/nutrisho/fetch-log";

  import AdvancedMode from "./AdvancedMode.svelte";
  import DraftEditor from "./DraftEditor.svelte";
  import type { ModelCheck } from "./model-check";
  import {
    listsProblem,
    modelProblem,
    saveProblem,
    type Problem,
  } from "./error-copy";

  /**
   * The sidebar (plan 012, M7): the draft, the save, and Advanced Mode below
   * them (M12). The right-click submenu sends text to a part of the draft.
   * Handed the ports, never a `browser.*` API, so its tests run against the
   * fakes.
   */
  const {
    clippings,
    drafts: draftStore,
    newId,
    subscribe,
    client,
    openSettings,
    isNewSession,
    settings,
    requestHostPermission,
    log,
    model,
    modelFor,
    modelSettings,
    watchModelSettings = () => () => {},
  }: {
    clippings: ClippingStore;
    drafts: DraftStore;
    /** A version 7 UUID for each new draft (D8). */
    newId: () => string;
    /** Called when another context stores a clipping; returns the unsubscribe. */
    subscribe: (onChange: () => void) => () => void;
    client: NutrishoClient;
    openSettings: () => void;
    /** True once per browser session: the drafts kept then open none. */
    isNewSession: () => Promise<boolean>;
    /** Where the server is; Advanced Mode changes it. */
    settings: SettingsStore;
    /** Asked first on the press that picks a server. */
    requestHostPermission: (pattern: string) => Promise<boolean>;
    /** What went to the server and back, shown in Advanced Mode. */
    log: readonly LogEntry[];
    /** The user's own model, which splits a group's lines on request (M13). */
    model: LineModel;
    /** The same, for a set-up other than the default, asked once (#183). */
    modelFor: (setup: ModelSetup) => LineModel;
    /** The set-ups and the default (#183): the built-in scan asks nothing. */
    modelSettings: ModelSettingsStore;
    /** Called when the set-ups change in storage; returns the unsubscribe. */
    watchModelSettings?: (onChange: () => void) => () => void;
  } = $props();

  let clipping = $state<Result<Clipping | undefined, StoreError> | undefined>(
    undefined,
  );
  let lists = $state<Result<Vocabulary, NutrishoError> | undefined>(undefined);
  // Raw, not deeply reactive: the drafts are replaced whole on every change,
  // and browser storage refuses to clone the Proxy a deep `$state` makes.
  let drafts = $state.raw<Drafts>(EMPTY_DRAFTS);
  let storeProblem = $state<string | undefined>(undefined);
  let issues = $state<readonly DraftIssue[]>([]);
  let saving = $state(false);
  let saveFailure = $state<Problem | undefined>(undefined);
  let modelOn = $state(false);
  let modelAddress = $state("");
  /** The default set-up's name, to say which model answered (#183). */
  let modelName = $state("The model");
  /** The set-ups other than the default, which a hold on *Ask* offers. */
  let otherSetups = $state.raw<readonly ModelSetup[]>([]);
  /** How long *Ask the model* is held to open the menu of the others. */
  let holdMs = $state(HOLD_MS);
  let modelCheck = $state<ModelCheck | undefined>(undefined);
  let asking = $state(false);
  /** What the model last changed, and how to take it back. */
  let modelNote = $state.raw<
    | {
        readonly draftId: string;
        readonly text: string;
        /** "rows", "steps" or "blurb", for the Undo button. */
        readonly changed: string;
        readonly undo: (onto: RecipeDraft) => RecipeDraft;
      }
    | undefined
  >(undefined);
  let modelFailure = $state<Problem | undefined>(undefined);
  /** Which draft's group, its steps or its blurb the model was last asked about. */
  let modelAt = $state.raw<
    | { readonly draftId: string; readonly at: number | "steps" | "blurb" }
    | undefined
  >(undefined);

  const draft = $derived(currentDraft(drafts));
  const saved = $derived(
    draft === undefined ? undefined : drafts.saved[draft.id],
  );
  const vocabulary = $derived(lists?.ok ? lists.value : EMPTY_VOCABULARY);

  /** Show the drafts, and keep them, so a draft survives the sidebar closing. */
  async function keep(next: Drafts) {
    if (next === drafts) return;
    drafts = next;
    const stored = await draftStore.save(next);
    storeProblem = stored.ok
      ? undefined
      : `Your drafts could not be kept: ${stored.error.message}`;
  }

  async function loadClipping() {
    clipping = await clippings.load();
    if (clipping.ok && clipping.value !== undefined) {
      await keep(afterClip(drafts, clipping.value, newId, vocabulary));
    }
  }

  // The lists come before the clipping, so lines sent from the submenu are
  // scanned against them.
  async function start() {
    const [stored, fresh] = await Promise.all([
      draftStore.load(),
      isNewSession(),
      loadModelOn(),
      loadLists(),
    ]);
    if (stored.ok) {
      // Kept across restarts, but a new session opens none of them.
      drafts = fresh ? { ...stored.value, current: undefined } : stored.value;
    } else
      storeProblem = `Your drafts could not be read: ${stored.error.message}`;
    await loadClipping();
  }

  async function loadModelOn() {
    const chosen = await modelSettings.load();
    const setup = chosen.ok ? chosenSetup(chosen.value) : undefined;
    modelOn = setup !== undefined;
    modelAddress = setup?.address ?? "";
    modelName = setup?.name ?? "The model";
    otherSetups = chosen.ok
      ? chosen.value.setups.filter((other) => other.id !== setup?.id)
      : [];
    holdMs = chosen.ok ? holdOf(chosen.value) : HOLD_MS;
    if (modelOn) void checkModel();
    else modelCheck = undefined;
  }

  /** Whether the model answers, so Advanced Mode can say (#182). */
  async function checkModel() {
    modelCheck = { kind: "checking" };
    const checked = await model.check();
    modelCheck = checked.ok
      ? { kind: "answering", address: modelAddress }
      : {
          kind: "problem",
          address: modelAddress,
          problem: modelProblem(checked.error),
        };
  }

  $effect(() => watchModelSettings(() => void loadModelOn()));

  async function loadLists() {
    lists = undefined;
    lists = await client.vocabulary();
  }

  // The lists load each time the sidebar opens (D4). A clip that lands while
  // they load waits for them and for the drafts kept, or it would start a
  // draft of its own.
  $effect(() => {
    const ready = untrack(() => start());
    return subscribe(() => void ready.then(loadClipping));
  });

  function edit(changed: RecipeDraft) {
    if (issues.length > 0) issues = checkDraft(changed, vocabulary.limits);
    void keep(withDraft(drafts, changed));
  }

  /** Start again: no clipping and no drafts. The settings stay. */
  async function clearAll() {
    issues = [];
    saveFailure = undefined;
    await keep(EMPTY_DRAFTS);
    const cleared = await clippings.clear();
    if (cleared.ok) clipping = { ok: true, value: undefined };
    else
      storeProblem = `The clipping could not be cleared: ${cleared.error.message}`;
  }

  async function save() {
    const sending = draft;
    if (sending === undefined) return;
    saveFailure = undefined;
    if (await flag(sending, checkDraft(sending, vocabulary.limits))) return;

    saving = true;
    const answer = await client.saveRecipe(sending);
    saving = false;
    if (answer.ok) {
      await keep(markSaved(drafts, sending.id, answer.value));
      await reloadLists();
      return;
    }
    // A refusal that names a field is flagged there, like the draft's own (M11).
    const refusal =
      answer.error.kind === "refused"
        ? explainRefusal(sending, answer.error.message)
        : undefined;
    if (refusal === undefined) saveFailure = saveProblem(answer.error);
    else await flag(sending, [refusal]);
  }

  /**
   * Send one group's lines to the user's own model, and take its rows where
   * they pass the checks (M13). Empty rows are left out of the question.
   */
  /** The default model, or another set-up for this one ask (#183). */
  function askerFor(setupId: string | undefined): {
    readonly asker: LineModel;
    readonly who: string;
  } {
    const other = otherSetups.find((setup) => setup.id === setupId);
    return other === undefined
      ? { asker: model, who: modelName }
      : { asker: modelFor(other), who: other.name };
  }

  async function askModel(groupIndex: number, setupId?: string) {
    const asked = draft;
    const group = asked?.groups[groupIndex];
    if (asked === undefined || group === undefined) return;
    const before = group.rows;
    const rows = before.filter((row) => lineOf(row) !== "");
    const lines = rows.map(lineOf);
    modelAt = { draftId: asked.id, at: groupIndex };
    modelNote = undefined;
    modelFailure = undefined;
    const { asker, who } = askerFor(setupId);
    asking = true;
    const answer = await asker.splitLines(lines);
    asking = false;
    if (!answer.ok) {
      modelFailure = modelProblem(answer.error);
      return;
    }
    // The user's units, once the lists are loaded: a model may take a word
    // of the line for one (#182).
    const units = vocabulary.units;
    const read = readModelAnswer(
      lines,
      answer.value,
      rows,
      units.length === 0 ? undefined : (unit) => knows(units, unit),
    );
    if (!read.ok) {
      modelFailure = {
        cause: read.error,
        action: "The rows are as they were. Try again, or edit them by hand.",
        fix: "retry",
      };
      return;
    }
    const current = currentDraft(drafts) ?? asked;
    await keep(
      withDraft(drafts, withGroupRows(current, groupIndex, read.value.rows)),
    );
    modelNote = {
      draftId: asked.id,
      text: describeSplit(lines.length, read.value, who),
      changed: "rows",
      undo: (onto) => withGroupRows(onto, groupIndex, before),
    };
  }

  /**
   * Send the steps to the user's own model, to rewrite short, precise and
   * colloquial (#181). A rewrite cannot be checked word for word, so it is
   * taken whole when its shape is right, and Undo puts the steps back.
   */
  async function askModelSteps(setupId?: string) {
    const asked = draft;
    if (asked === undefined) return;
    const before = asked.steps;
    const steps = before.filter(
      (step) => step.title.trim() !== "" || step.text.trim() !== "",
    );
    if (steps.length === 0) return;
    modelAt = { draftId: asked.id, at: "steps" };
    modelNote = undefined;
    modelFailure = undefined;
    const { asker, who } = askerFor(setupId);
    asking = true;
    const answer = await asker.rewriteSteps(steps);
    asking = false;
    if (!answer.ok) {
      modelFailure = modelProblem(answer.error);
      return;
    }
    const read = readStepsAnswer(answer.value);
    if (!read.ok) {
      modelFailure = {
        cause: read.error,
        action: "The steps are as they were. Try again, or edit them by hand.",
        fix: "retry",
      };
      return;
    }
    const current = currentDraft(drafts) ?? asked;
    await keep(withDraft(drafts, withSteps(current, read.value)));
    modelNote = {
      draftId: asked.id,
      text: describeSteps(steps.length, read.value.length, who),
      changed: "steps",
      undo: (onto) => withSteps(onto, before),
    };
  }

  /**
   * Send the blurb to the user's own model, to compact and put in English
   * (#205). Taken whole when its shape is right, as the steps are, and Undo
   * puts the blurb back.
   */
  async function askModelBlurb(setupId?: string) {
    const asked = draft;
    if (asked === undefined || asked.blurb.trim() === "") return;
    const before = asked.blurb;
    modelAt = { draftId: asked.id, at: "blurb" };
    modelNote = undefined;
    modelFailure = undefined;
    const { asker, who } = askerFor(setupId);
    asking = true;
    const answer = await asker.rewriteBlurb(before);
    asking = false;
    if (!answer.ok) {
      modelFailure = modelProblem(answer.error);
      return;
    }
    const read = readBlurbAnswer(answer.value);
    if (!read.ok) {
      modelFailure = {
        cause: read.error,
        action: "The blurb is as it was. Try again, or edit it by hand.",
        fix: "retry",
      };
      return;
    }
    const current = currentDraft(drafts) ?? asked;
    await keep(
      withDraft(drafts, withDetails(current, { blurb: read.value.blurb })),
    );
    modelNote = {
      draftId: asked.id,
      text: describeBlurb(who, read.value.language),
      changed: "blurb",
      undo: (onto) => withDetails(onto, { blurb: before }),
    };
  }

  async function undoModel() {
    const note = modelNote;
    const current = currentDraft(drafts);
    modelNote = undefined;
    if (note === undefined || current?.id !== note.draftId) return;
    await keep(withDraft(drafts, note.undo(current)));
  }

  /** Show what stops a save at its fields; true if anything does. */
  async function flag(
    sending: RecipeDraft,
    found: readonly DraftIssue[],
  ): Promise<boolean> {
    issues = found;
    // One group is open at a time: open the one the first problem is in.
    const inGroup = found
      .map((issue) => /^groups\.(\d+)\./.exec(issue.field)?.[1])
      .find((group) => group !== undefined);
    if (inGroup !== undefined) {
      await keep(withDraft(drafts, withOpenGroup(sending, Number(inGroup))));
    }
    return found.length > 0;
  }

  /**
   * After a save, which may have made names of the user's own (M8). The lists
   * shown stay until the new ones come, and stay if they do not.
   */
  async function reloadLists() {
    const fresh = await client.vocabulary();
    if (fresh.ok) lists = fresh;
  }

  const problem = $derived(
    lists !== undefined && !lists.ok ? listsProblem(lists.error) : undefined,
  );
</script>

<!-- What the model is doing, or did: shown beside the button pressed. -->
{#snippet modelFeedback()}
  {#if asking}
    <p class="quiet" role="status">Asking the model…</p>
  {:else if modelFailure !== undefined}
    <div class="problem" role="alert">
      <p>{modelFailure.cause}</p>
      <p>{modelFailure.action}</p>
    </div>
    {#if modelFailure.fix === "settings"}
      <button type="button" onclick={openSettings}>Open settings</button>
    {/if}
  {:else if modelNote !== undefined}
    <div class="model-note" role="status">
      <p>{modelNote.text}</p>
      <button type="button" onclick={() => void undoModel()}
        >Undo the model's {modelNote.changed}</button
      >
    </div>
  {/if}
{/snippet}

<main>
  <header>
    <h1>Nutrisho clipper</h1>
    <button type="button" onclick={() => void clearAll()}>Clear all</button>
  </header>

  <!-- The requests are in Advanced Mode's log; only a problem shows here. -->
  {#if problem !== undefined}
    <section aria-label="Your lists">
      <div class="problem" role="alert">
        <p>{problem.cause}</p>
        <p>{problem.action}</p>
      </div>
      {#if problem.fix === "settings"}
        <button type="button" onclick={openSettings}>Open settings</button>
      {:else}
        <button type="button" onclick={() => void loadLists()}>Try again</button
        >
      {/if}
    </section>
  {/if}
  {#if clipping !== undefined && clipping.ok && clipping.value === undefined && draft === undefined}
    <div class="hint">
      <img
        class="plate"
        src="/img/plate-lineout.webp"
        width="1400"
        height="1107"
        alt="Watercolour of a rugby lineout: a player in yellow, lifted high, reaches for a cauliflower thrown in place of the ball, while players of both teams, among them a greyhound, a rhino, a bull and a bear, brace below."
      />
      <p>Nothing clipped yet.</p>
      <p class="quiet">
        Select text on a page, then choose <em>Clip into Nutrisho</em> from the right-click
        menu and where the text goes: the title, the blurb, an ingredient group or
        the steps. Alt+Shift+N and the toolbar button send it to a new ingredient
        group.
      </p>
    </div>
  {/if}

  {#if storeProblem !== undefined}
    <p class="problem" role="alert">{storeProblem}</p>
  {/if}

  {#if drafts.drafts.length > 1 || (drafts.drafts.length > 0 && draft === undefined)}
    <label class="drafts">
      Draft
      <select
        value={drafts.current ?? ""}
        onchange={(event) =>
          void keep(choose(drafts, event.currentTarget.value))}
      >
        {#if draft === undefined}
          <option value="" disabled>Choose a draft…</option>
        {/if}
        {#each drafts.drafts as held (held.id)}
          <option value={held.id}>{held.name || "Untitled"}</option>
        {/each}
      </select>
    </label>
  {/if}

  {#if draft !== undefined}
    <DraftEditor
      {draft}
      {vocabulary}
      {issues}
      onChange={edit}
      onAskModel={modelOn
        ? (group, setupId) => void askModel(group, setupId)
        : undefined}
      onAskModelBlurb={modelOn
        ? (setupId) => void askModelBlurb(setupId)
        : undefined}
      onAskModelSteps={modelOn
        ? (setupId) => void askModelSteps(setupId)
        : undefined}
      otherModels={otherSetups}
      defaultModel={modelName}
      {holdMs}
      {asking}
      modelAt={modelAt?.draftId === draft.id ? modelAt.at : undefined}
      {modelFeedback}
    />

    <section aria-labelledby="save-heading" class="save">
      <h2 id="save-heading" class="hidden">Save</h2>
      {#if issues.length > 0}
        <div class="problem" role="alert">
          <p>This recipe cannot be saved yet:</p>
          <ul>
            {#each issues as issue (issue.field)}
              <li>{issue.message}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if saveFailure !== undefined}
        <div class="problem" role="alert">
          <p>{saveFailure.cause}</p>
          <p>{saveFailure.action}</p>
        </div>
        {#if saveFailure.fix === "settings"}
          <button type="button" onclick={openSettings}>Open settings</button>
        {/if}
      {/if}
      {#if saved !== undefined}
        <div role="status">
          {#if saved.created}
            <p>Saved as {saved.name}.</p>
          {:else}
            <p>
              Already saved, so nothing changed: make further changes in
              Nutrisho.
            </p>
          {/if}
          {#if saved.renamed}
            <p>Its name was taken, so Nutrisho gave it another.</p>
          {/if}
          {#if saved.inTrash}
            <p>It is in the trash in Nutrisho.</p>
          {/if}
          {#each saved.warnings as warning, index (index)}
            <p class="quiet">{warning}</p>
          {/each}
          <a href={saved.openUrl} target="_blank" rel="noreferrer"
            >Open in Nutrisho</a
          >
        </div>
      {/if}
      <div class="actions">
        <button
          type="button"
          class="primary"
          disabled={saving}
          onclick={() => void save()}>{saving ? "Clipping…" : "Clip"}</button
        >
        <button
          type="button"
          class="quiet-button"
          onclick={() => void keep(discard(drafts, draft.id))}
          >Discard this draft</button
        >
      </div>
    </section>
  {/if}

  <section aria-label="Clipping" class="clipping">
    {#if clipping === undefined}
      <p class="quiet">Loading…</p>
    {:else if !clipping.ok}
      <p class="problem" role="alert">
        The last clipping could not be read: {clipping.error.message}
      </p>
    {:else if clipping.value !== undefined}
      <p class="source">
        From
        <a href={clipping.value.url} target="_blank" rel="noreferrer"
          >{clipping.value.title || clipping.value.url}</a
        >
      </p>
      {#each clipping.value.warnings as warning (warning.kind)}
        <p class="problem">{warning.message}</p>
      {/each}
    {/if}
    <!-- The server, and the log: folded away until opened. -->
    <AdvancedMode
      {settings}
      {modelSettings}
      onModelsChanged={() => void loadModelOn()}
      {requestHostPermission}
      onServerChanged={() => void loadLists()}
      {log}
      {modelCheck}
      onCheckModel={modelOn ? () => void checkModel() : undefined}
    />
  </section>
</main>

<style>
  /* The site's look is global (styles/clipper.css); this is layout only. */
  main {
    display: grid;
    gap: 1.5rem;
    padding: 1rem;
  }

  section {
    display: grid;
    gap: 0.5rem;
  }

  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .hint {
    display: grid;
    gap: 0.5rem;
    text-align: center;
  }

  .plate {
    width: 80%;
  }

  .drafts {
    display: grid;
    gap: 0.125rem;
  }

  .save,
  [role="status"] {
    display: grid;
    gap: 0.5rem;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    justify-content: space-between;
  }

  .problem ul {
    margin: 0;
    padding-left: 1.25rem;
  }

  .source {
    color: var(--pencil);
    font-size: 0.875rem;
  }

  button {
    justify-self: start;
  }
</style>
