<script lang="ts">
  import { untrack } from "svelte";

  import type { SettingsStore } from "@/core/ports/types";
  import {
    DEFAULT_SETTINGS,
    SERVERS,
    hostPatternFor,
    serverParts,
    serverUrlFor,
  } from "@/core/settings";

  import type { LogEntry } from "@/nutrisho/fetch-log";

  /**
   * Advanced Mode (plan 012, M12): folded away under the recipe, where the
   * clipboard was. It picks the server, this computer at the address Django
   * prints or nutrisho.com, and its port, and keeps a log of what the clipper
   * did. Handed the ports, never a `browser.*` API.
   */
  const {
    settings,
    requestHostPermission,
    onServerChanged,
    log,
  }: {
    settings: SettingsStore;
    /** Called first on the press: Firefox refuses one made after an `await`. */
    requestHostPermission: (pattern: string) => Promise<boolean>;
    /** The server changed, so the lists are loaded again from it. */
    onServerChanged: () => void;
    /** What went to the server and back, oldest first. */
    log: readonly LogEntry[];
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

  $effect(() => {
    untrack(() => void load());
  });

  async function load() {
    const stored = await settings.load();
    if (!stored.ok) return;
    ({ host, port } = serverParts(stored.value.serverUrl));
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
