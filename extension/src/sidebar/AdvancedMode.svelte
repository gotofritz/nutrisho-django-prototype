<script lang="ts">
  import { untrack } from "svelte";

  import {
    NO_CHOICES,
    chooseSetup,
    holdOf,
    removeSetup,
    saveSetup,
    withHold,
    type ModelChoices,
    type ModelSetup,
    type UnsavedSetup,
  } from "@/core/model-settings";
  import type { ModelSettingsStore, SettingsStore } from "@/core/ports/types";
  import {
    DEFAULT_SETTINGS,
    SERVERS,
    hostPatternFor,
    serverParts,
    serverUrlFor,
  } from "@/core/settings";

  import type { LogEntry } from "@/nutrisho/fetch-log";

  import type { ModelCheck } from "./model-check";
  import SetupForm from "./SetupForm.svelte";

  /**
   * Advanced Mode (plan 012, M12): folded away under the recipe, where the
   * clipboard was. It picks the server, this computer at the address Django
   * prints or nutrisho.com, and its port, and keeps a log of what the clipper
   * did. Since #183 it also holds the user's own models, and which one
   * *Ask the model* uses. Handed the ports, never a `browser.*` API.
   */
  const {
    settings,
    modelSettings,
    onModelsChanged,
    requestHostPermission,
    onServerChanged,
    log,
    modelCheck,
    onCheckModel,
  }: {
    settings: SettingsStore;
    /** The user's own models, and the default (#183). */
    modelSettings: ModelSettingsStore;
    /** A set-up or the default changed, so the sidebar loads it again. */
    onModelsChanged: () => void;
    /** Called first on the press: Firefox refuses one made after an `await`. */
    requestHostPermission: (pattern: string) => Promise<boolean>;
    /** The server changed, so the lists are loaded again from it. */
    onServerChanged: () => void;
    /** What went to the server and back, oldest first. */
    log: readonly LogEntry[];
    /** How the last check of the user's own model went (#182). */
    modelCheck?: ModelCheck;
    /** Check it again; undefined while no model is set up. */
    onCheckModel?: () => void;
  } = $props();

  /** The time on the clock, as hh:mm:ss. */
  function clock(at: Date): string {
    return [at.getHours(), at.getMinutes(), at.getSeconds()]
      .map((part) => String(part).padStart(2, "0"))
      .join(":");
  }

  let host = $state(serverParts(DEFAULT_SETTINGS.serverUrl).host);
  let port = $state(serverParts(DEFAULT_SETTINGS.serverUrl).port);
  let status = $state<
    | { kind: "idle" }
    | { kind: "using"; serverUrl: string }
    | { kind: "problem"; message: string }
  >({ kind: "idle" });

  let models = $state.raw<ModelChoices>(NO_CHOICES);
  /** The set-up form: closed, a new set-up, or one being changed. */
  let editing = $state.raw<
    { kind: "closed" } | { kind: "new" } | { kind: "edit"; setup: ModelSetup }
  >({ kind: "closed" });
  let modelStatus = $state<
    | { kind: "idle" }
    | { kind: "saved"; name: string }
    | { kind: "refused"; name: string; address: string }
    | { kind: "problem"; message: string }
  >({ kind: "idle" });

  $effect(() => {
    untrack(() => void load());
  });

  async function load() {
    const [stored, storedModels] = await Promise.all([
      settings.load(),
      modelSettings.load(),
    ]);
    if (storedModels.ok) models = storedModels.value;
    if (!stored.ok) return;
    ({ host, port } = serverParts(stored.value.serverUrl));
  }

  /** Keep the set-ups, and tell the sidebar. */
  async function keepModels(next: ModelChoices) {
    const written = await modelSettings.save(next);
    if (!written.ok) return written;
    models = next;
    onModelsChanged();
    return written;
  }

  async function changeModels(next: ModelChoices) {
    modelStatus = { kind: "idle" };
    const written = await keepModels(next);
    if (!written.ok) {
      modelStatus = {
        kind: "problem",
        message: `Your models could not be saved: ${written.error.message}`,
      };
    }
  }

  /** The hold that opens *Ask the model*'s menu, as typed in seconds. */
  async function changeHold(typed: string) {
    const next = withHold(models, typed);
    if (next.ok) await changeModels(next.value);
    else modelStatus = { kind: "problem", message: next.error };
  }

  function saveOne(setup: UnsavedSetup) {
    return keepModels(saveSetup(models, setup));
  }

  /** Each server starts at its own port. */
  function pick(next: string) {
    host = next;
    port = SERVERS.find((server) => server.host === next)?.port ?? "";
    status = { kind: "idle" };
  }

  async function use() {
    const serverUrl = serverUrlFor({ host, port });
    if (!serverUrl.ok) {
      status = { kind: "problem", message: serverUrl.error };
      return;
    }
    // First, and synchronously: the gesture's task must not have yielded.
    const asking = requestHostPermission(hostPatternFor(serverUrl.value));
    const granted = await asking;
    const current = await settings.load();
    const saved = await settings.save({
      ...(current.ok ? current.value : DEFAULT_SETTINGS),
      serverUrl: serverUrl.value,
    });
    if (!saved.ok) {
      status = {
        kind: "problem",
        message: `The server could not be saved: ${saved.error.message}`,
      };
      return;
    }
    status = granted
      ? { kind: "using", serverUrl: serverUrl.value }
      : {
          kind: "problem",
          message: `Saved, but the clipper was not allowed to reach ${serverUrl.value}. Press Use this server again and allow it when the browser asks.`,
        };
    onServerChanged();
  }
</script>

<details class="advanced">
  <summary>Advanced Mode</summary>
  <div class="server">
    <label>
      Server
      <select
        value={host}
        onchange={(event) => pick(event.currentTarget.value)}
      >
        {#each SERVERS as server (server.host)}
          <option value={server.host}>{server.label}</option>
        {/each}
      </select>
    </label>
    <label class="port">
      Port
      <input
        type="text"
        inputmode="numeric"
        autocomplete="off"
        placeholder={host === SERVERS[1]?.host ? "443" : ""}
        bind:value={port}
      />
    </label>
  </div>
  <button type="button" onclick={() => void use()}>Use this server</button>
  {#if status.kind === "using"}
    <p role="status">Now using {status.serverUrl}.</p>
  {:else if status.kind === "problem"}
    <p class="problem" role="alert">{status.message}</p>
  {/if}
  <section class="models" aria-labelledby="models-heading">
    <h3 id="models-heading">Your models</h3>
    <label>
      Default model
      <select
        value={models.chosen ?? ""}
        onchange={(event) =>
          void changeModels(
            chooseSetup(models, event.currentTarget.value || undefined),
          )}
      >
        <option value="">Built in</option>
        {#each models.setups as setup (setup.id)}
          <option value={setup.id}>{setup.name}</option>
        {/each}
      </select>
    </label>
    {#if models.setups.length > 0}
      <label>
        Hold Ask the model for (seconds)
        <input
          type="number"
          min="0.5"
          max="5"
          step="0.5"
          value={holdOf(models) / 1000}
          onchange={(event) => void changeHold(event.currentTarget.value)}
        />
      </label>
      <p class="quiet">
        Holding it that long, or a right-click, picks another model once.
      </p>
    {/if}
    {#if models.setups.length === 0}
      <p class="quiet">
        No models of your own yet: the built-in scan reads the lines. A model
        can split harder lines, and rewrite the steps short.
      </p>
    {:else}
      <ul>
        {#each models.setups as setup (setup.id)}
          <li>
            <span>{setup.name}</span>
            <button
              type="button"
              class="icon"
              aria-label="Edit {setup.name}"
              title="Edit"
              onclick={() => {
                modelStatus = { kind: "idle" };
                editing = { kind: "edit", setup };
              }}>✎</button
            >
            <button
              type="button"
              class="icon"
              aria-label="Delete {setup.name}"
              title="Delete"
              onclick={() => void changeModels(removeSetup(models, setup.id))}
              >×</button
            >
          </li>
        {/each}
      </ul>
    {/if}
    {#if editing.kind === "closed"}
      <button
        type="button"
        class="add"
        onclick={() => {
          modelStatus = { kind: "idle" };
          editing = { kind: "new" };
        }}>+ add model</button
      >
    {:else}
      {#key editing}
        <SetupForm
          choices={models}
          {...editing.kind === "edit" ? { editing: editing.setup } : {}}
          {requestHostPermission}
          onSave={saveOne}
          onDone={({ name, refused }) => {
            editing = { kind: "closed" };
            modelStatus =
              refused === undefined
                ? { kind: "saved", name }
                : { kind: "refused", name, address: refused };
          }}
          onCancel={() => (editing = { kind: "closed" })}
        />
      {/key}
    {/if}
    {#if modelStatus.kind === "saved"}
      <p role="status">Saved {modelStatus.name}.</p>
    {:else if modelStatus.kind === "refused"}
      <p role="status">
        Saved {modelStatus.name}, but the clipper was not allowed to reach {modelStatus.address},
        so it cannot ask it. Edit it, save again and allow it when the browser
        asks.
      </p>
    {:else if modelStatus.kind === "problem"}
      <p class="problem" role="alert">{modelStatus.message}</p>
    {/if}
  </section>
  {#if onCheckModel !== undefined}
    <div class="model">
      {#if modelCheck?.kind === "checking"}
        <p role="status">Checking your model…</p>
      {:else if modelCheck?.kind === "answering"}
        <p role="status">Your model answers at {modelCheck.address}.</p>
      {:else if modelCheck?.kind === "problem"}
        <p class="problem" role="alert">
          Checked {modelCheck.address}: {modelCheck.problem.cause}
          {modelCheck.problem.action}
        </p>
      {/if}
      <button
        type="button"
        disabled={modelCheck?.kind === "checking"}
        onclick={() => onCheckModel()}>Check the model</button
      >
    </div>
  {/if}
  <section class="log" aria-labelledby="log-heading">
    <h3 id="log-heading">Log</h3>
    <ol role="log" aria-labelledby="log-heading">
      {#each log as entry, index (index)}
        <li>
          <time datetime={entry.at.toISOString()}>{clock(entry.at)}</time>
          {entry.text}
        </li>
      {:else}
        <li class="quiet">Nothing yet.</li>
      {/each}
    </ol>
  </section>
</details>

<style>
  .advanced[open] {
    display: grid;
    gap: 0.5rem;
  }

  summary {
    cursor: pointer;
  }

  .server {
    display: grid;
    grid-template-columns: 1fr 5rem;
    gap: 0.5rem;
  }

  label {
    display: grid;
    gap: 0.125rem;
    font-size: 0.875rem;
  }

  button {
    justify-self: start;
  }

  .model,
  .models {
    display: grid;
    gap: 0.25rem;
  }

  .models {
    margin-top: 0.75rem;
  }

  .models ul {
    display: grid;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .models li {
    display: flex;
    align-items: baseline;
    gap: 0.25rem;
  }

  .models li > span {
    flex: 1;
  }

  .icon {
    min-width: 1.75rem;
    padding: 0.25rem;
    font-size: 0.875rem;
  }

  .log {
    display: grid;
    gap: 0.25rem;
  }

  /* A tool's log, not the storybook: plain monospace. It scrolls once long. */
  .log ol {
    color: var(--ink);
    font:
      0.75rem/1.4 ui-monospace,
      monospace;
    list-style: none;
    margin: 0;
    max-height: 12rem;
    overflow: auto;
    padding: 0;
  }

  .log li {
    white-space: pre-wrap;
    word-break: break-all;
  }

  time {
    color: var(--pencil);
  }
</style>
