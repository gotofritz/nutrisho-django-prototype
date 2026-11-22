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
  import type {
    ClippingStore,
    DraftStore,
    NutrishoClient,
    NutrishoError,
    SettingsStore,
    StoreError,
  } from "@/core/ports/types";
  import {
    checkDraft,
    explainRefusal,
    type DraftIssue,
    withOpenGroup,
    type RecipeDraft,
  } from "@/core/recipe-draft";
  import type { Result } from "@/core/result";
  import { EMPTY_VOCABULARY, type Vocabulary } from "@/core/vocabulary";
  import type { LogEntry } from "@/nutrisho/fetch-log";

  import AdvancedMode from "./AdvancedMode.svelte";
  import DraftEditor from "./DraftEditor.svelte";
  import { listsProblem, saveProblem, type Problem } from "./error-copy";

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
      loadLists(),
    ]);
    if (stored.ok) {
      // Kept across restarts, but a new session opens none of them.
      drafts = fresh ? { ...stored.value, current: undefined } : stored.value;
    } else
      storeProblem = `Your drafts could not be read: ${stored.error.message}`;
    await loadClipping();
  }

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
    <DraftEditor {draft} {vocabulary} {issues} onChange={edit} />

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
          onclick={() => void save()}>{saving ? "Saving…" : "Save"}</button
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
      {requestHostPermission}
      onServerChanged={() => void loadLists()}
      {log}
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
