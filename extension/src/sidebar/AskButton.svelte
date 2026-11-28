<script lang="ts">
  import { tick } from "svelte";

  import { HOLD_MS } from "@/core/model-settings";

  /**
   * *Ask the model* (M13): a click asks the default set-up; a hold (a
   * second, unless the user set another), a right-click, the context-menu
   * key or Shift+Enter open a menu of the other set-ups, to ask one of them
   * once (#183). The default heads the menu, faded, as a reminder.
   */
  const {
    label,
    others,
    current,
    holdMs = HOLD_MS,
    disabled,
    onAsk,
  }: {
    /** The button's accessible name, which says what is asked about. */
    label: string;
    /** The set-ups other than the default, in their order. */
    others: readonly { readonly id: string; readonly name: string }[];
    /** The default set-up's name, shown in the menu but not to be picked. */
    current?: string;
    /** How long a press is held before the menu opens. */
    holdMs?: number;
    disabled: boolean;
    /** Asks the set-up with this id, or the default when there is none. */
    onAsk: (setupId?: string) => void;
  } = $props();

  const seconds = $derived(holdMs / 1000);
  const hint = $derived(
    `Hold for ${seconds} ${seconds === 1 ? "second" : "seconds"}, right-click or press Shift+Enter to ask another model once`,
  );

  let open = $state(false);
  /** A hold is under way: the button fills while it lasts. */
  let holding = $state(false);
  /** The hold opened the menu, so the click that ends it asks nothing. */
  let held = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let wrapper = $state<HTMLElement>();
  let button = $state<HTMLButtonElement>();
  let menu = $state<HTMLElement>();

  const more = $derived(others.length > 0);

  function items(): HTMLElement[] {
    return [
      ...(menu?.querySelectorAll<HTMLElement>(
        "[role=menuitem]:not(:disabled)",
      ) ?? []),
    ];
  }

  async function openMenu() {
    open = true;
    await tick();
    items()[0]?.focus();
  }

  function shut(refocus: boolean) {
    open = false;
    held = false;
    if (refocus) button?.focus();
  }

  function press(event: PointerEvent) {
    if (!more || event.button > 0) return;
    held = false;
    letGo();
    holding = true;
    timer = setTimeout(() => {
      timer = undefined;
      holding = false;
      held = true;
      void openMenu();
    }, holdMs);
  }

  function letGo() {
    clearTimeout(timer);
    timer = undefined;
    holding = false;
  }

  function click() {
    if (held) {
      held = false;
      return;
    }
    onAsk(undefined);
  }

  function contextMenu(event: MouseEvent) {
    if (!more) return;
    event.preventDefault();
    // A long touch ends in this rather than the timer: no click must follow.
    if (timer !== undefined) held = true;
    letGo();
    void openMenu();
  }

  function buttonKey(event: KeyboardEvent) {
    if (!more || event.key !== "Enter" || !event.shiftKey) return;
    event.preventDefault();
    void openMenu();
  }

  function menuKey(event: KeyboardEvent, index: number) {
    const all = items();
    const step: Record<string, number> = {
      ArrowDown: index + 1,
      ArrowUp: index - 1,
      Home: 0,
      End: all.length - 1,
    };
    const to = step[event.key];
    if (to !== undefined) {
      event.preventDefault();
      all[(to + all.length) % all.length]?.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      shut(true);
    } else if (event.key === "Tab") {
      shut(false);
    }
  }

  function pick(id: string) {
    shut(true);
    onAsk(id);
  }

  function pressElsewhere(event: PointerEvent) {
    if (open && !wrapper?.contains(event.target as Node)) shut(false);
  }
</script>

<svelte:document onpointerdown={pressElsewhere} />

<span class="ask" bind:this={wrapper}>
  <button
    bind:this={button}
    type="button"
    class:holding
    style:--hold="{holdMs}ms"
    aria-label={label}
    aria-haspopup={more ? "menu" : undefined}
    aria-expanded={more ? open : undefined}
    title={more ? hint : undefined}
    {disabled}
    onclick={click}
    onpointerdown={press}
    onpointerup={letGo}
    onpointerleave={letGo}
    onpointercancel={letGo}
    oncontextmenu={contextMenu}
    onkeydown={buttonKey}>Ask the model</button
  >
  {#if open}
    <ul
      class="ask-menu"
      role="menu"
      aria-label="Ask another model"
      bind:this={menu}
    >
      {#if current !== undefined}
        <li role="none">
          <button type="button" role="menuitem" tabindex="-1" disabled
            >{current} (default)</button
          >
        </li>
      {/if}
      {#each others as other, index (other.id)}
        <li role="none">
          <button
            type="button"
            role="menuitem"
            tabindex="-1"
            onclick={() => pick(other.id)}
            onkeydown={(event) => menuKey(event, index)}>{other.name}</button
          >
        </li>
      {/each}
    </ul>
  {/if}
</span>

<style>
  /* The look is global (styles/clipper.css); this is layout only. */
  .ask {
    position: relative;
    display: inline-block;
  }

  .ask-menu {
    position: absolute;
    top: calc(100% + 0.25rem);
    right: 0;
    z-index: 2;
    min-width: 12rem;
    margin: 0;
    padding: 0.25rem 0;
    list-style: none;
  }

  .ask-menu button {
    display: block;
    width: 100%;
    text-align: left;
  }
</style>
