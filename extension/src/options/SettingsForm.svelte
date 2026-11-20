<script lang="ts">
  import { untrack } from "svelte";

  import type { SettingsStore, StoreError } from "@/core/ports/types";
  import {
    DEFAULT_SETTINGS,
    checkSettings,
    hostPatternFor,
    type SettingsField,
    type SettingsIssue,
  } from "@/core/settings";

  /**
   * The options page's form (plan 012, M6): where the user's Nutrisho is,
   * and the API key that signs the clipper in. Handed the ports, never a
   * `browser.*` API, so its tests run against the fakes.
   */
  const {
    settings,
    requestHostPermission,
  }: {
    settings: SettingsStore;
    /**
     * Ask the browser for a host, by its match pattern. Firefox refuses a
     * request made outside a user gesture, so it is called first on Save,
     * before anything is awaited.
     */
    requestHostPermission: (pattern: string) => Promise<boolean>;
  } = $props();

  let serverUrl = $state(DEFAULT_SETTINGS.serverUrl);
  /** What is typed; the saved key is never shown again (D11). */
  let apiKey = $state("");
  let savedKey = $state("");
  let loadError = $state<StoreError | undefined>(undefined);
  let issues = $state<readonly SettingsIssue[]>([]);
  let status = $state<
    | { kind: "idle" | "saving" | "saved" }
    | { kind: "refused"; serverUrl: string }
    | { kind: "failed"; error: StoreError }
  >({ kind: "idle" });

  $effect(() => {
    untrack(() => void load());
  });

  async function load() {
    const stored = await settings.load();
    loadError = stored.ok ? undefined : stored.error;
    const current = stored.ok ? stored.value : DEFAULT_SETTINGS;
    serverUrl = current.serverUrl;
    savedKey = current.apiKey;
  }

  function issueFor(field: SettingsField): SettingsIssue | undefined {
    return issues.find((issue) => issue.field === field);
  }

  async function submit(event: Event) {
    event.preventDefault();
    const checked = checkSettings({
      serverUrl,
      apiKey: apiKey.trim() === "" ? savedKey : apiKey,
    });
    if (!checked.ok) {
      issues = checked.error;
      status = { kind: "idle" };
      return;
    }
    issues = [];

    // First, and synchronously: Firefox refuses a permission request made
    // after the gesture's task has yielded.
    const asking = requestHostPermission(
      hostPatternFor(checked.value.serverUrl),
    );
    status = { kind: "saving" };
    const granted = await asking;

    const saved = await settings.save(checked.value);
    if (!saved.ok) {
      status = { kind: "failed", error: saved.error };
      return;
    }
    savedKey = checked.value.apiKey;
    apiKey = "";
    serverUrl = checked.value.serverUrl;
    status = granted
      ? { kind: "saved" }
      : { kind: "refused", serverUrl: checked.value.serverUrl };
  }
</script>

<form class="settings" onsubmit={submit} novalidate>
  <h1>Nutrisho clipper settings</h1>

  {#if loadError !== undefined}
    <p class="problem" role="alert">
      Your saved settings could not be read, so these are the defaults. ({loadError.message})
    </p>
  {/if}

  <div class="field">
    <label for="server-url">Your Nutrisho's address</label>
    <input
      id="server-url"
      type="url"
      autocomplete="url"
      bind:value={serverUrl}
      aria-invalid={issueFor("serverUrl") !== undefined}
      aria-describedby={issueFor("serverUrl") === undefined
        ? "server-url-hint"
        : "server-url-issue"}
    />
    {#if issueFor("serverUrl") !== undefined}
      <p class="problem" id="server-url-issue">
        {issueFor("serverUrl")?.message}
      </p>
    {:else}
      <p class="quiet" id="server-url-hint">
        <code>make dev</code> serves it at http://localhost:8987.
      </p>
    {/if}
  </div>

  <div class="field">
    <label for="api-key">API key</label>
    <input
      id="api-key"
      type="password"
      autocomplete="off"
      spellcheck="false"
      bind:value={apiKey}
      aria-invalid={issueFor("apiKey") !== undefined}
      aria-describedby={issueFor("apiKey") === undefined
        ? "api-key-hint"
        : "api-key-issue"}
    />
    {#if issueFor("apiKey") !== undefined}
      <p class="problem" id="api-key-issue">{issueFor("apiKey")?.message}</p>
    {:else if savedKey !== ""}
      <p class="quiet" id="api-key-hint">
        A key is saved. Leave this empty to keep it, or paste a new one.
      </p>
    {:else}
      <p class="quiet" id="api-key-hint">
        Make one with
        <code
          >make manage ARGS="create_api_token &lt;username&gt; --name clipper"</code
        >.
      </p>
    {/if}
  </div>

  <button type="submit" disabled={status.kind === "saving"}>Save</button>

  {#if status.kind === "saved"}
    <p role="status">Saved.</p>
  {:else if status.kind === "refused"}
    <p role="status">
      Saved, but the clipper was not allowed to reach {status.serverUrl}, so it
      cannot load your lists. Save again and allow it when the browser asks.
    </p>
  {:else if status.kind === "failed"}
    <p class="problem" role="alert">
      Your settings could not be saved: {status.error.message}
    </p>
  {/if}
</form>

<style>
  .settings {
    display: grid;
    gap: 1rem;
    max-width: 36rem;
    margin: 1.5rem;
    font:
      1rem/1.5 system-ui,
      sans-serif;
  }

  .field {
    display: grid;
    gap: 0.25rem;
  }

  .quiet {
    margin: 0;
    color: GrayText;
    font-size: 0.875rem;
  }

  .problem {
    margin: 0;
    color: #a40e26;
  }

  button {
    justify-self: start;
  }
</style>
