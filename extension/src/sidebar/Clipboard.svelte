<script lang="ts">
  import type { DraftTarget } from "@/core/recipe-draft";

  /**
   * Where captured text lands (plan 012, D3). Typed or pasted text is the
   * same: the buttons send the part selected, or all of it, to the name,
   * blurb, ingredients or steps, after what is there or in its place.
   */
  let {
    text = $bindable(),
    onSend,
  }: {
    text: string;
    onSend: (
      target: DraftTarget,
      mode: "add" | "replace",
      text: string,
    ) => void;
  } = $props();

  let box: HTMLTextAreaElement | undefined = $state();

  const TARGETS: readonly { target: DraftTarget; label: string }[] = [
    { target: "name", label: "name" },
    { target: "blurb", label: "blurb" },
    { target: "group", label: "ingredient groups" },
    { target: "steps", label: "steps" },
  ];

  function send(target: DraftTarget, mode: "add" | "replace") {
    const start = box?.selectionStart ?? 0;
    const end = box?.selectionEnd ?? 0;
    onSend(target, mode, end > start ? text.slice(start, end) : text);
  }
</script>

<label class="clipboard">
  Clipboard
  <textarea bind:this={box} bind:value={text} rows="6"></textarea>
</label>
<p class="quiet">Select part of it to send only that part.</p>
<div class="targets">
  {#each TARGETS as { target, label } (target)}
    <span class="target">{label}</span>
    <button
      type="button"
      aria-label="Add to {label}"
      disabled={text.trim() === ""}
      onclick={() => send(target, "add")}>Add</button
    >
    <button
      type="button"
      aria-label="Replace {label}"
      disabled={text.trim() === ""}
      onclick={() => send(target, "replace")}>Replace</button
    >
  {/each}
</div>

<style>
  .clipboard {
    display: grid;
    gap: 0.125rem;
    font-size: 0.875rem;
  }

  textarea {
    font: inherit;
  }

  .quiet {
    margin: 0;
    color: GrayText;
    font-size: 0.875rem;
  }

  .targets {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.25rem 0.5rem;
    align-items: center;
  }

  .target {
    text-transform: capitalize;
  }
</style>
