<script lang="ts">
  import { untrack } from "svelte";

  import {
    BACKENDS,
    BUILT_IN,
    checkModelSettings,
    defaultsFor,
    modelHostPattern,
    type ModelBackend,
    type ModelField,
    type ModelIssue,
    type ModelSettings,
  } from "@/core/model-settings";
  import type { ModelSettingsStore, StoreError } from "@/core/ports/types";

  /**
   * The line scanner (plan 012, M13): the built-in scan, or the user's own
   * model on MLX, llama.cpp or Anthropic. Handed the ports, never a
   * `browser.*` API.
   */
  const {
    store,
    requestHostPermission,
  }: {
    store: ModelSettingsStore;
    /** Called first on Save: Firefox refuses one made after an `await`. */
    requestHostPermission: (pattern: string) => Promise<boolean>;
  } = $props();

  let chosen = $state<ModelSettings>(BUILT_IN);
  /** What is typed; a saved key is never shown again (D11). */
  let typedKey = $state("");
  /** The saved choice, whose key stays while its backend does. */
  let saved = $state<ModelSettings>(BUILT_IN);
  let issues = $state<readonly ModelIssue[]>([]);
  let status = $state<
    | { kind: "idle" | "saved" }
    | { kind: "refused"; address: string }
    | { kind: "failed"; error: StoreError }
  >({ kind: "idle" });

  const local = $derived(
    chosen.backend === "mlx" || chosen.backend === "llama",
  );

  $effect(() => {
    untrack(() => void load());
  });

  async function load() {
    const stored = await store.load();
    if (stored.ok) {
      chosen = stored.value;
      saved = stored.value;
    }
  }

  function issueFor(field: ModelField): ModelIssue | undefined {
    return issues.find((issue) => issue.field === field);
  }

  /** Each backend starts where timbuktu's guide starts it. */
  function pick(backend: ModelBackend) {
    chosen = defaultsFor(backend);
    typedKey = "";
    issues = [];
    status = { kind: "idle" };
  }

  async function submit(event: Event) {
    event.preventDefault();
    const keptKey = chosen.backend === saved.backend ? saved.key : "";
    const checked = checkModelSettings({
      ...chosen,
      key: typedKey.trim() === "" ? keptKey : typedKey,
    });
    if (!checked.ok) {
      issues = checked.error;
      status = { kind: "idle" };
      return;
    }
    issues = [];
    // First, and synchronously: the gesture's task must not have yielded.
    const pattern = modelHostPattern(checked.value);
    const asking =
      pattern === undefined
        ? Promise.resolve(true)
        : requestHostPermission(pattern);
    const granted = await asking;

    const written = await store.save(checked.value);
    if (!written.ok) {
      status = { kind: "failed", error: written.error };
      return;
    }
    chosen = checked.value;
    saved = checked.value;
    typedKey = "";
    status = granted
      ? { kind: "saved" }
      : { kind: "refused", address: checked.value.address };
  }
</script>

<form class="model" onsubmit={submit} novalidate>
  <h2>Ingredient lines</h2>
  <p class="quiet">
    The built-in scan reads each line with your lists. A model of your own can
    split harder lines, and rewrite the steps short; it is sent a group's lines,
    or the steps, and nothing else, when you ask it to.
  </p>

  <div class="field">
    <label for="model-backend">Line scanner</label>
    <select
      id="model-backend"
      value={chosen.backend}
      onchange={(event) => pick(event.currentTarget.value as ModelBackend)}
    >
      {#each BACKENDS as backend (backend.id)}
        <option value={backend.id}>{backend.label}</option>
      {/each}
    </select>
  </div>

  {#if local}
    <div class="field">
      <label for="model-address">Address</label>
      <input
        id="model-address"
        type="url"
        autocomplete="off"
        bind:value={
          () => chosen.address, (address) => (chosen = { ...chosen, address })
        }
        aria-invalid={issueFor("address") !== undefined}
        aria-describedby={issueFor("address") === undefined
          ? undefined
          : "model-address-issue"}
      />
      {#if issueFor("address") !== undefined}
        <p class="problem" id="model-address-issue">
          {issueFor("address")?.message}
        </p>
      {/if}
    </div>
  {/if}

  {#if chosen.backend !== "built-in"}
    <div class="field">
      <label for="model-name">Model</label>
      <input
        id="model-name"
        type="text"
        autocomplete="off"
        spellcheck="false"
        bind:value={
          () => chosen.model, (model) => (chosen = { ...chosen, model })
        }
        aria-invalid={issueFor("model") !== undefined}
        aria-describedby={issueFor("model") === undefined
          ? "model-name-hint"
          : "model-name-issue"}
      />
      {#if issueFor("model") !== undefined}
        <p class="problem" id="model-name-issue">
          {issueFor("model")?.message}
        </p>
      {:else}
        <p class="quiet" id="model-name-hint">
          {#if chosen.backend === "llama"}
            Leave it empty when the server has one model loaded.
          {:else if chosen.backend === "mlx"}
            The one the server was started with.
          {:else}
            Any current Claude model.
          {/if}
        </p>
      {/if}
    </div>
  {/if}

  {#if chosen.backend !== "built-in"}
    <div class="field">
      <label for="model-key"
        >{chosen.backend === "anthropic"
          ? "Anthropic key"
          : "Server key"}</label
      >
      <input
        id="model-key"
        type="password"
        autocomplete="off"
        spellcheck="false"
        bind:value={typedKey}
        aria-invalid={issueFor("key") !== undefined}
        aria-describedby={issueFor("key") === undefined
          ? "model-key-hint"
          : "model-key-issue"}
      />
      {#if issueFor("key") !== undefined}
        <p class="problem" id="model-key-issue">{issueFor("key")?.message}</p>
      {:else if saved.key !== "" && saved.backend === chosen.backend}
        <p class="quiet" id="model-key-hint">
          A key is saved. Leave this empty to keep it, or paste a new one.
        </p>
      {:else if chosen.backend === "anthropic"}
        <p class="quiet" id="model-key-hint">
          Make a key for the clipper alone, with a low spending limit, in the
          Anthropic Console, so it can be revoked on its own. It is kept in this
          browser and sent only to Anthropic.
        </p>
      {:else}
        <p class="quiet" id="model-key-hint">
          Only if the server asks for one.
        </p>
      {/if}
    </div>
  {/if}

  <button type="submit">Save the line scanner</button>

  {#if status.kind === "saved"}
    <p role="status">Saved.</p>
  {:else if status.kind === "refused"}
    <p role="status">
      Saved, but the clipper was not allowed to reach {status.address}, so it
      cannot ask the model. Save again and allow it when the browser asks.
    </p>
  {:else if status.kind === "failed"}
    <p class="problem" role="alert">
      The line scanner could not be saved: {status.error.message}
    </p>
  {/if}
</form>

<style>
  /* The site's look is global (styles/clipper.css); this is layout only. */
  .model {
    display: grid;
    gap: 1.5rem;
    max-width: 36rem;
    margin: 1.5rem;
  }

  .field {
    display: grid;
    gap: 0.25rem;
  }

  button {
    justify-self: start;
  }
</style>
