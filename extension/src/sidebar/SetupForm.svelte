<script lang="ts">
  import {
    BACKENDS,
    checkModelSettings,
    checkSetupName,
    defaultsFor,
    modelHostPattern,
    suggestName,
    type ModelBackend,
    type ModelChoices,
    type ModelField,
    type ModelIssue,
    type ModelSettings,
    type ModelSetup,
    type UnsavedSetup,
  } from "@/core/model-settings";
  import type { StoreError } from "@/core/ports/types";
  import type { Result } from "@/core/result";

  /**
   * One of the user's own models, made or changed in Advanced Mode (#183):
   * MLX, llama.cpp or Anthropic, under a name. It was the options page's one
   * model (plan 012, M13). Handed the ports, never a `browser.*` API.
   */
  const {
    choices,
    editing,
    requestHostPermission,
    onSave,
    onDone,
    onCancel,
  }: {
    /** Every set-up, so a name is not taken twice. */
    choices: ModelChoices;
    /** The set-up being changed; none for a new one. */
    editing?: ModelSetup;
    /** Called first on Save: Firefox refuses one made after an `await`. */
    requestHostPermission: (pattern: string) => Promise<boolean>;
    onSave: (setup: UnsavedSetup) => Promise<Result<void, StoreError>>;
    /** Saved; `refused` is the address the browser would not let it reach. */
    onDone: (outcome: { name: string; refused?: string }) => void;
    onCancel: () => void;
  } = $props();

  // The form starts from the set-up it was opened on, and is not told again.
  const start = (() => editing)();
  const BACKENDS_TO_SET_UP = BACKENDS.filter(
    (backend) => backend.id !== "built-in",
  );

  let chosen = $state<ModelSettings>(start ?? defaultsFor("mlx"));
  let name = $state(start?.name ?? suggestName(defaultsFor("mlx")));
  /** Once a name is typed, it stays whatever the set-up runs. */
  let named = $state(start !== undefined);
  /** What is typed; a saved key is never shown again (D11). */
  let typedKey = $state("");
  let issues = $state<readonly ModelIssue[]>([]);
  let nameIssue = $state<string | undefined>(undefined);
  let failure = $state<StoreError | undefined>(undefined);

  const local = $derived(
    chosen.backend === "mlx" || chosen.backend === "llama",
  );
  const keySaved = $derived(
    start !== undefined && start.key !== "" && start.backend === chosen.backend,
  );

  function issueFor(field: ModelField): ModelIssue | undefined {
    return issues.find((issue) => issue.field === field);
  }

  function change(next: ModelSettings) {
    chosen = next;
    if (!named) name = suggestName(next);
  }

  /** Each backend starts where timbuktu's guide starts it. */
  function pick(backend: ModelBackend) {
    change(defaultsFor(backend));
    typedKey = "";
    issues = [];
  }

  async function submit(event: Event) {
    event.preventDefault();
    const keptKey = keySaved ? (start?.key ?? "") : "";
    const checked = checkModelSettings({
      ...chosen,
      key: typedKey.trim() === "" ? keptKey : typedKey,
    });
    nameIssue = checkSetupName({ name, choices, id: start?.id });
    issues = checked.ok ? [] : checked.error;
    if (!checked.ok || nameIssue !== undefined) return;
    // First, and synchronously: the gesture's task must not have yielded.
    const pattern = modelHostPattern(checked.value);
    const asking =
      pattern === undefined
        ? Promise.resolve(true)
        : requestHostPermission(pattern);
    const granted = await asking;

    const setup: UnsavedSetup = {
      ...checked.value,
      name: name.trim(),
      ...(start === undefined ? {} : { id: start.id }),
    };
    const written = await onSave(setup);
    if (!written.ok) {
      failure = written.error;
      return;
    }
    onDone(
      granted
        ? { name: setup.name }
        : { name: setup.name, refused: setup.address },
    );
  }
</script>

<form class="setup open" onsubmit={submit} novalidate>
  <div class="field">
    <label for="setup-backend">Runs on</label>
    <select
      id="setup-backend"
      value={chosen.backend}
      onchange={(event) => pick(event.currentTarget.value as ModelBackend)}
    >
      {#each BACKENDS_TO_SET_UP as backend (backend.id)}
        <option value={backend.id}>{backend.label}</option>
      {/each}
    </select>
  </div>

  {#if local}
    <div class="field">
      <label for="setup-address">Address</label>
      <input
        id="setup-address"
        type="url"
        autocomplete="off"
        bind:value={
          () => chosen.address, (address) => change({ ...chosen, address })
        }
        aria-invalid={issueFor("address") !== undefined}
        aria-describedby={issueFor("address") === undefined
          ? undefined
          : "setup-address-issue"}
      />
      {#if issueFor("address") !== undefined}
        <p class="problem" id="setup-address-issue">
          {issueFor("address")?.message}
        </p>
      {/if}
    </div>
  {/if}

  <div class="field">
    <label for="setup-model">Model</label>
    <input
      id="setup-model"
      type="text"
      autocomplete="off"
      spellcheck="false"
      bind:value={() => chosen.model, (model) => change({ ...chosen, model })}
      aria-invalid={issueFor("model") !== undefined}
      aria-describedby={issueFor("model") === undefined
        ? "setup-model-hint"
        : "setup-model-issue"}
    />
    {#if issueFor("model") !== undefined}
      <p class="problem" id="setup-model-issue">
        {issueFor("model")?.message}
      </p>
    {:else}
      <p class="quiet" id="setup-model-hint">
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

  <div class="field">
    <label for="setup-key">
      {chosen.backend === "anthropic" ? "Anthropic key" : "Server key"}
    </label>
    <input
      id="setup-key"
      type="password"
      autocomplete="off"
      spellcheck="false"
      bind:value={typedKey}
      aria-invalid={issueFor("key") !== undefined}
      aria-describedby={issueFor("key") === undefined
        ? "setup-key-hint"
        : "setup-key-issue"}
    />
    {#if issueFor("key") !== undefined}
      <p class="problem" id="setup-key-issue">{issueFor("key")?.message}</p>
    {:else if keySaved}
      <p class="quiet" id="setup-key-hint">
        A key is saved. Leave this empty to keep it, or paste a new one.
      </p>
    {:else if chosen.backend === "anthropic"}
      <p class="quiet" id="setup-key-hint">
        Make the clipper a key in a workspace of its own, with a low spend
        limit, in the Anthropic Console, so it can be capped and revoked on its
        own. It is kept in this browser and sent only to Anthropic.
      </p>
    {:else}
      <p class="quiet" id="setup-key-hint">Only if the server asks for one.</p>
    {/if}
  </div>

  <div class="field">
    <label for="setup-name">Name</label>
    <input
      id="setup-name"
      type="text"
      autocomplete="off"
      bind:value={
        () => name,
        (typed) => {
          name = typed;
          named = true;
        }
      }
      aria-invalid={nameIssue !== undefined}
      aria-describedby={nameIssue === undefined
        ? undefined
        : "setup-name-issue"}
    />
    {#if nameIssue !== undefined}
      <p class="problem" id="setup-name-issue">{nameIssue}</p>
    {/if}
  </div>

  <div class="actions">
    <button type="submit">Save the set-up</button>
    <button type="button" onclick={() => onCancel()}>Cancel</button>
  </div>

  {#if failure !== undefined}
    <p class="problem" role="alert">
      The set-up could not be saved: {failure.message}
    </p>
  {/if}
</form>

<style>
  /* The site's look is global (styles/clipper.css); this is layout only. */
  .setup {
    display: grid;
    gap: 0.75rem;
    padding: 0.5rem 0.5rem 0.75rem;
  }

  .field {
    display: grid;
    gap: 0.125rem;
  }

  label {
    font-size: 0.875rem;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
  }
</style>
