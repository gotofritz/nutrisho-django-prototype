<script lang="ts">
  import { untrack } from "svelte";

  import type { Clipping } from "@/core/clipping";
  import type {
    ClippingStore,
    NutrishoClient,
    StoreError,
  } from "@/core/ports/types";
  import type { Result } from "@/core/result";
  import type { Vocabulary } from "@/core/vocabulary";
  import type { NutrishoError } from "@/core/ports/types";

  import { listsProblem } from "./error-copy";

  /**
   * The sidebar (plan 012, M6): the last clipping, and whether the user's
   * lists loaded. Nothing is a recipe yet; M7 makes the clipping a draft.
   * Handed the ports, never a `browser.*` API, so its tests run against the
   * fakes.
   */
  const {
    clippings,
    subscribe,
    client,
    openSettings,
  }: {
    clippings: ClippingStore;
    /** Called when another context stores a clipping; returns the unsubscribe. */
    subscribe: (onChange: () => void) => () => void;
    client: NutrishoClient;
    openSettings: () => void;
  } = $props();

  let clipping = $state<Result<Clipping | undefined, StoreError> | undefined>(
    undefined,
  );
  let lists = $state<Result<Vocabulary, NutrishoError> | undefined>(undefined);

  async function loadClipping() {
    clipping = await clippings.load();
  }

  async function loadLists() {
    lists = undefined;
    lists = await client.vocabulary();
  }

  // The lists load each time the sidebar opens (D4).
  $effect(() => {
    untrack(() => {
      void loadClipping();
      void loadLists();
    });
    return subscribe(() => void loadClipping());
  });

  function count(n: number, one: string, many: string): string {
    return `${n} ${n === 1 ? one : many}`;
  }

  const problem = $derived(
    lists !== undefined && !lists.ok ? listsProblem(lists.error) : undefined,
  );
</script>

<main>
  <h1>Nutrisho clipper</h1>

  <section aria-labelledby="clipping-heading">
    <h2 id="clipping-heading">Clipping</h2>
    {#if clipping === undefined}
      <p class="quiet">Loading…</p>
    {:else if !clipping.ok}
      <p class="problem" role="alert">
        The last clipping could not be read: {clipping.error.message}
      </p>
    {:else if clipping.value === undefined}
      <p>Nothing clipped yet.</p>
      <p class="quiet">
        Select text on a page, then choose <em>Clip into Nutrisho</em> from the right-click
        menu, press Alt+Shift+N, or click the toolbar button.
      </p>
    {:else}
      <p class="source">
        From
        <a href={clipping.value.url} target="_blank" rel="noreferrer"
          >{clipping.value.title || clipping.value.url}</a
        >
      </p>
      <ul class="lines">
        {#each clipping.value.text.split("\n") as line, index (index)}
          <li>{line}</li>
        {/each}
      </ul>
      {#each clipping.value.warnings as warning (warning.kind)}
        <p class="problem">{warning.message}</p>
      {/each}
    {/if}
  </section>

  <section aria-labelledby="lists-heading">
    <h2 id="lists-heading">Your lists</h2>
    {#if lists === undefined}
      <p class="quiet">Loading your lists…</p>
    {:else if lists.ok}
      <p>
        Lists loaded for {lists.value.user}: {count(
          lists.value.ingredients.length,
          "ingredient",
          "ingredients",
        )}, {count(lists.value.units.length, "unit", "units")}, {count(
          lists.value.cuisines.length,
          "cuisine",
          "cuisines",
        )}, {count(lists.value.tags.length, "tag", "tags")}.
      </p>
    {:else if problem !== undefined}
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
    {/if}
  </section>
</main>

<style>
  main {
    display: grid;
    gap: 1rem;
    padding: 0.75rem;
    font:
      0.9375rem/1.5 system-ui,
      sans-serif;
  }

  h1,
  h2,
  p {
    margin: 0;
  }

  h1 {
    font-size: 1.25rem;
  }

  h2 {
    font-size: 1rem;
  }

  section {
    display: grid;
    gap: 0.5rem;
  }

  .lines {
    margin: 0;
    padding-left: 1.25rem;
  }

  .quiet,
  .source {
    color: GrayText;
    font-size: 0.875rem;
  }

  .problem {
    color: #a40e26;
  }

  button {
    justify-self: start;
  }
</style>
