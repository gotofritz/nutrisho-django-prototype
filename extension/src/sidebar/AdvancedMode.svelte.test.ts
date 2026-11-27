import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import {
  defaultsFor,
  type ModelChoices,
  type ModelSetup,
} from "@/core/model-settings";
import {
  createFakeModelSettingsStore,
  type FakeModelSettingsStore,
} from "@/core/ports/fakes/fake-model-settings-store";
import {
  createFakeSettingsStore,
  type FakeSettingsStore,
} from "@/core/ports/fakes/fake-settings-store";
import type { LogEntry } from "@/nutrisho/fetch-log";

import AdvancedMode from "./AdvancedMode.svelte";
import type { ModelCheck } from "./model-check";

const KEY = "nsh_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";

function renderAdvanced(
  options: {
    settings?: FakeSettingsStore;
    granted?: boolean;
    log?: readonly LogEntry[];
    modelCheck?: ModelCheck;
    checkModel?: boolean;
    models?: FakeModelSettingsStore;
  } = {},
) {
  const settings =
    options.settings ??
    createFakeSettingsStore({
      serverUrl: "http://127.0.0.1:8987",
      apiKey: KEY,
    });
  const requestHostPermission = vi.fn<(pattern: string) => Promise<boolean>>(
    async () => options.granted ?? true,
  );
  const onServerChanged = vi.fn<() => void>();
  const onCheckModel = vi.fn<() => void>();
  const onModelsChanged = vi.fn<() => void>();
  const models = options.models ?? createFakeModelSettingsStore();
  render(AdvancedMode, {
    settings,
    modelSettings: models,
    onModelsChanged,
    requestHostPermission,
    onServerChanged,
    log: options.log ?? [],
    ...(options.checkModel === true ? { onCheckModel } : {}),
    ...(options.modelCheck === undefined
      ? {}
      : { modelCheck: options.modelCheck }),
  });
  return {
    settings,
    requestHostPermission,
    onServerChanged,
    onCheckModel,
    onModelsChanged,
    models,
  };
}

async function open() {
  await fireEvent.click(screen.getByText("Advanced Mode"));
}

async function stored(settings: FakeSettingsStore) {
  const loaded = await settings.load();
  return loaded.ok ? loaded.value : undefined;
}

// Plan 012, M12: the clipboard went; its fold stays, as Advanced Mode, where
// the server is picked.
describe("Advanced Mode", () => {
  it("is folded away until opened", async () => {
    renderAdvanced();

    expect(
      await screen.findByRole("combobox", { name: "Server" }),
    ).not.toBeVisible();
    await open();
    expect(screen.getByRole("combobox", { name: "Server" })).toBeVisible();
  });

  it("starts from the saved server and port", async () => {
    renderAdvanced();
    await open();

    expect(await screen.findByDisplayValue("8987")).toBeVisible();
    expect(
      screen.getByRole<HTMLSelectElement>("combobox", { name: "Server" }).value,
    ).toBe("127.0.0.1");
  });

  it("switches to nutrisho.com, asking for it first and keeping the key", async () => {
    const { settings, requestHostPermission, onServerChanged } =
      renderAdvanced();
    await open();
    await screen.findByDisplayValue("8987");

    await fireEvent.change(screen.getByRole("combobox", { name: "Server" }), {
      target: { value: "nutrisho.com" },
    });
    expect(screen.getByRole("textbox", { name: "Port" })).toHaveValue("");
    await fireEvent.click(
      screen.getByRole("button", { name: "Use this server" }),
    );

    expect(requestHostPermission).toHaveBeenCalledWith(
      "https://nutrisho.com/*",
    );
    expect(
      await screen.findByText("Now using https://nutrisho.com."),
    ).toBeVisible();
    expect(await stored(settings)).toEqual({
      serverUrl: "https://nutrisho.com",
      apiKey: KEY,
    });
    expect(onServerChanged).toHaveBeenCalledOnce();
  });

  it("takes another port on this computer", async () => {
    const { settings } = renderAdvanced();
    await open();
    await fireEvent.input(await screen.findByDisplayValue("8987"), {
      target: { value: "8000" },
    });

    await fireEvent.click(
      screen.getByRole("button", { name: "Use this server" }),
    );

    await screen.findByText("Now using http://127.0.0.1:8000.");
    expect((await stored(settings))?.serverUrl).toBe("http://127.0.0.1:8000");
  });

  it("refuses a port that is not one, and changes nothing", async () => {
    const { settings, requestHostPermission, onServerChanged } =
      renderAdvanced();
    await open();
    await fireEvent.input(await screen.findByDisplayValue("8987"), {
      target: { value: "eighty" },
    });

    await fireEvent.click(
      screen.getByRole("button", { name: "Use this server" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The port is a whole number from 1 to 65535.",
    );
    expect(requestHostPermission).not.toHaveBeenCalled();
    expect(onServerChanged).not.toHaveBeenCalled();
    expect((await stored(settings))?.serverUrl).toBe("http://127.0.0.1:8987");
  });

  it("says when the browser would not let it reach the server", async () => {
    renderAdvanced({ granted: false });
    await open();
    await screen.findByDisplayValue("8987");

    await fireEvent.click(
      screen.getByRole("button", { name: "Use this server" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /not allowed to reach http:\/\/127\.0\.0\.1:8987/,
    );
  });

  // #179: the page's markup was the clipboard again, so it went too.
  it("shows no markup from the page", async () => {
    renderAdvanced();
    await open();

    expect(screen.queryByRole("textbox", { name: "Page HTML" })).toBeNull();
  });

  it("shows the log of requests and replies, oldest first, with the time", async () => {
    renderAdvanced({
      log: [
        {
          at: new Date(2026, 10, 22, 5, 20, 1),
          text: "→ GET http://127.0.0.1:8987/recipes/api/vocabulary/",
        },
        {
          at: new Date(2026, 10, 22, 5, 20, 2),
          text: "← 200 OK · 15 B · 42 ms",
        },
      ],
    });
    await open();

    const entries = within(
      screen.getByRole("log", { name: "Log" }),
    ).getAllByRole("listitem");
    expect(entries.map((entry) => entry.textContent)).toEqual([
      "05:20:01 → GET http://127.0.0.1:8987/recipes/api/vocabulary/",
      "05:20:02 ← 200 OK · 15 B · 42 ms",
    ]);
    expect(entries[0]).toBeVisible();
  });

  it("says when nothing is logged yet", async () => {
    renderAdvanced();
    await open();

    expect(screen.getByRole("log", { name: "Log" })).toHaveTextContent(
      "Nothing yet.",
    );
  });

  // #182: whether the model answers, before it is asked anything.
  it("says nothing of a model while none is set up", async () => {
    renderAdvanced();
    await open();

    expect(
      screen.queryByRole("button", { name: "Check the model" }),
    ).toBeNull();
  });

  it.each([
    [{ kind: "checking" }, "Checking your model…"],
    [
      { kind: "answering", address: "http://localhost:8080" },
      "Your model answers at http://localhost:8080.",
    ],
    [
      {
        kind: "problem",
        address: "http://localhost:8080",
        problem: {
          cause: "Nothing answered at your model's address.",
          action: "Start its server, or check the address, then try again.",
          fix: "retry",
        },
      },
      "Checked http://localhost:8080: Nothing answered at your model's address. Start its server, or check the address, then try again.",
    ],
  ] as const)(
    "says how the model's check went: %j",
    async (modelCheck, said) => {
      renderAdvanced({ modelCheck, checkModel: true });
      await open();

      expect(
        screen.getByText(said, {
          normalizer: (text) => text.replace(/\s+/g, " ").trim(),
        }),
      ).toBeVisible();
    },
  );

  it("checks the model again on request", async () => {
    const { onCheckModel } = renderAdvanced({
      modelCheck: { kind: "answering", address: "http://localhost:8080" },
      checkModel: true,
    });
    await open();

    await fireEvent.click(
      screen.getByRole("button", { name: "Check the model" }),
    );

    expect(onCheckModel).toHaveBeenCalledTimes(1);
  });
});

// #183: several set-ups, made here, and the default picked here.
const MLX: ModelSetup = { ...defaultsFor("mlx"), id: "1", name: "Qwen on MLX" };
const HAIKU: ModelSetup = {
  ...defaultsFor("anthropic"),
  key: "sk-ant-api03-clipper",
  id: "2",
  name: "Haiku",
};
const BOTH: ModelChoices = { setups: [MLX, HAIKU], chosen: "1" };

async function choices(models: FakeModelSettingsStore) {
  const loaded = await models.load();
  return loaded.ok ? loaded.value : undefined;
}

describe("your models", () => {
  it("picks the default from the built-in scan and your set-ups", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    const { onModelsChanged } = renderAdvanced({ models });
    await open();

    const pulldown = await screen.findByRole("combobox", {
      name: "Default model",
    });
    await vi.waitFor(() => expect(pulldown).toHaveValue("1"));
    expect(
      within(pulldown)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Built in", "Qwen on MLX", "Haiku"]);

    await fireEvent.change(pulldown, { target: { value: "2" } });

    await vi.waitFor(async () =>
      expect((await choices(models))?.chosen).toBe("2"),
    );
    expect(onModelsChanged).toHaveBeenCalled();
  });

  it("goes back to the built-in scan", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    renderAdvanced({ models });
    await open();
    const pulldown = await screen.findByRole("combobox", {
      name: "Default model",
    });
    await vi.waitFor(() => expect(pulldown).toHaveValue("1"));

    await fireEvent.change(pulldown, { target: { value: "" } });

    await vi.waitFor(async () =>
      expect((await choices(models))?.chosen).toBeUndefined(),
    );
  });

  // Asked for in the #205 PR: the hold that opens the menu of the others.
  it("sets how long Ask the model is held, a second to begin with", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    const { onModelsChanged } = renderAdvanced({ models });
    await open();
    const hold = await screen.findByRole("spinbutton", {
      name: "Hold Ask the model for (seconds)",
    });
    await vi.waitFor(() => expect(hold).toHaveValue(1));

    await fireEvent.change(hold, { target: { value: "2.5" } });

    await vi.waitFor(async () =>
      expect((await choices(models))?.holdMs).toBe(2500),
    );
    expect(onModelsChanged).toHaveBeenCalled();
  });

  it("refuses a hold out of range, and keeps the one there was", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    renderAdvanced({ models });
    await open();
    const hold = await screen.findByRole("spinbutton", {
      name: "Hold Ask the model for (seconds)",
    });

    await fireEvent.change(hold, { target: { value: "9" } });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Hold for between 0.5 and 5 seconds.",
    );
    expect((await choices(models))?.holdMs).toBeUndefined();
  });

  it("says when there are no set-ups yet", async () => {
    renderAdvanced();
    await open();

    expect(await screen.findByText(/No models of your own yet/)).toBeVisible();
  });

  it("adds a set-up, which the list then shows", async () => {
    const { models, onModelsChanged, requestHostPermission } = renderAdvanced();
    await open();

    await fireEvent.click(screen.getByRole("button", { name: "+ add model" }));
    await fireEvent.click(
      screen.getByRole("button", { name: "Save the set-up" }),
    );

    expect(
      await screen.findByText("Saved Qwen3-8B-4bit on MLX."),
    ).toBeVisible();
    expect(requestHostPermission).toHaveBeenCalledWith("http://localhost/*");
    expect((await choices(models))?.setups).toHaveLength(1);
    expect(onModelsChanged).toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Save the set-up" }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Edit Qwen3-8B-4bit on MLX" }),
    ).toBeVisible();
  });

  it("edits a set-up", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    renderAdvanced({ models });
    await open();

    await fireEvent.click(
      await screen.findByRole("button", { name: "Edit Haiku" }),
    );
    await fireEvent.input(screen.getByLabelText("Name"), {
      target: { value: "Claude" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Save the set-up" }),
    );

    expect(await screen.findByText("Saved Claude.")).toBeVisible();
    expect((await choices(models))?.setups[1]).toEqual({
      ...HAIKU,
      name: "Claude",
    });
  });

  it("deletes a set-up", async () => {
    const models = createFakeModelSettingsStore(BOTH);
    const { onModelsChanged } = renderAdvanced({ models });
    await open();

    await fireEvent.click(
      await screen.findByRole("button", { name: "Delete Haiku" }),
    );

    await vi.waitFor(async () =>
      expect((await choices(models))?.setups).toEqual([MLX]),
    );
    expect(screen.queryByRole("button", { name: "Edit Haiku" })).toBeNull();
    expect(onModelsChanged).toHaveBeenCalled();
  });

  it("says when the browser would not let it reach the model", async () => {
    renderAdvanced({ granted: false });
    await open();

    await fireEvent.click(screen.getByRole("button", { name: "+ add model" }));
    await fireEvent.click(
      screen.getByRole("button", { name: "Save the set-up" }),
    );

    expect(
      await screen.findByText(
        /Saved Qwen3-8B-4bit on MLX, but the clipper was not allowed to reach http:\/\/localhost:8080/,
      ),
    ).toBeVisible();
  });
});
