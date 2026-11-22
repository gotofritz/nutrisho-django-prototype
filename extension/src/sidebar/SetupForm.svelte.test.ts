import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import {
  NO_CHOICES,
  defaultsFor,
  type ModelChoices,
  type ModelSetup,
  type UnsavedSetup,
} from "@/core/model-settings";
import type { StoreError } from "@/core/ports/types";
import { err, ok, type Result } from "@/core/result";

import SetupForm from "./SetupForm.svelte";

const KEY = "sk-ant-api03-clipper";

const HAIKU: ModelSetup = {
  ...defaultsFor("anthropic"),
  key: KEY,
  id: "2",
  name: "Haiku",
};
const CHOICES: ModelChoices = { setups: [HAIKU], chosen: "2" };

function renderForm(
  options: {
    choices?: ModelChoices;
    editing?: ModelSetup;
    granted?: boolean;
    saved?: Result<void, StoreError>;
  } = {},
) {
  const requestHostPermission = vi.fn<(pattern: string) => Promise<boolean>>(
    async () => options.granted ?? true,
  );
  const onSave = vi.fn<
    (setup: UnsavedSetup) => Promise<Result<void, StoreError>>
  >(async () => options.saved ?? ok(undefined));
  const onDone = vi.fn<(outcome: { name: string; refused?: string }) => void>();
  const onCancel = vi.fn<() => void>();
  render(SetupForm, {
    choices: options.choices ?? NO_CHOICES,
    ...(options.editing === undefined ? {} : { editing: options.editing }),
    requestHostPermission,
    onSave,
    onDone,
    onCancel,
  });
  return { requestHostPermission, onSave, onDone, onCancel };
}

async function pick(backend: string) {
  await fireEvent.change(screen.getByRole("combobox", { name: "Runs on" }), {
    target: { value: backend },
  });
}

async function fill(label: string, value: string) {
  await fireEvent.input(screen.getByLabelText(label), { target: { value } });
}

async function save() {
  await fireEvent.click(
    screen.getByRole("button", { name: "Save the set-up" }),
  );
}

// #183: a set-up is made in the sidebar, as the options page made the one
// model before (M13).
describe("the set-up form", () => {
  it("starts a new set-up on MLX, named after its model", () => {
    renderForm();

    expect(screen.getByRole("combobox", { name: "Runs on" })).toHaveValue(
      "mlx",
    );
    expect(screen.getByLabelText("Name")).toHaveValue("Qwen3-8B-4bit on MLX");
    expect(screen.getByLabelText("Address")).toHaveValue(
      "http://localhost:8080",
    );
  });

  it("offers the three backends, not the built-in scan", () => {
    renderForm();

    const offered = Array.from(
      screen
        .getByRole("combobox", { name: "Runs on" })
        .querySelectorAll("option"),
      (option) => option.value,
    );
    expect(offered).toEqual(["mlx", "llama", "anthropic"]);
  });

  it("names it after what it runs until a name is typed", async () => {
    renderForm();

    await pick("llama");
    expect(screen.getByLabelText("Name")).toHaveValue("llama.cpp");
    await fill("Model", "qwen3");
    expect(screen.getByLabelText("Name")).toHaveValue("qwen3 on llama.cpp");

    await fill("Name", "Mine");
    await pick("anthropic");
    expect(screen.getByLabelText("Name")).toHaveValue("Mine");
  });

  it("asks for the model's host first, then saves", async () => {
    const { requestHostPermission, onSave, onDone } = renderForm();
    await fill("Address", "http://127.0.0.1:8080/");

    await save();

    expect(requestHostPermission).toHaveBeenCalledWith("http://127.0.0.1/*");
    expect(onSave).toHaveBeenCalledWith({
      ...defaultsFor("mlx"),
      address: "http://127.0.0.1:8080",
      name: "Qwen3-8B-4bit on MLX",
    });
    expect(onDone).toHaveBeenCalledWith({ name: "Qwen3-8B-4bit on MLX" });
  });

  it("sets Anthropic up with your key, and no address to type", async () => {
    const { requestHostPermission, onSave } = renderForm();
    await pick("anthropic");

    expect(screen.queryByLabelText("Address")).toBeNull();
    expect(screen.queryByLabelText("Server key")).toBeNull();
    expect(screen.getByLabelText("Anthropic key")).toHaveAccessibleDescription(
      /a key for the clipper alone, with a low spending limit/,
    );
    await fill("Anthropic key", KEY);
    await save();

    expect(requestHostPermission).toHaveBeenCalledWith(
      "https://api.anthropic.com/*",
    );
    expect(onSave).toHaveBeenCalledWith({
      ...defaultsFor("anthropic"),
      key: KEY,
      name: "claude-haiku-5-5 on Anthropic",
    });
  });

  it("edits a set-up, keeping its saved key when the field is left empty", async () => {
    const { onSave } = renderForm({ choices: CHOICES, editing: HAIKU });

    expect(screen.getByLabelText("Name")).toHaveValue("Haiku");
    // D11: a saved key is never shown again.
    expect(screen.getByLabelText("Anthropic key")).toHaveValue("");
    expect(screen.getByLabelText("Anthropic key")).toHaveAccessibleDescription(
      /A key is saved\. Leave this empty to keep it/,
    );

    await save();

    expect(onSave).toHaveBeenCalledWith(HAIKU);
  });

  it("does not carry a key over to another backend", async () => {
    const { onSave } = renderForm({ choices: CHOICES, editing: HAIKU });
    await pick("llama");

    await save();

    expect(onSave.mock.lastCall?.[0]).toMatchObject({
      id: "2",
      name: "Haiku",
      backend: "llama",
      key: "",
    });
  });

  it("says when the Anthropic key is missing", async () => {
    const { onSave } = renderForm();
    await pick("anthropic");

    await save();

    expect(screen.getByLabelText("Anthropic key")).toHaveAccessibleDescription(
      "Enter your Anthropic key.",
    );
    expect(onSave).not.toHaveBeenCalled();
  });

  it("names what is wrong at its field, and saves nothing", async () => {
    const { requestHostPermission, onSave } = renderForm();
    await fill("Address", "http://192.168.1.5:8080");
    await fill("Model", "");
    await fill("Name", "");

    await save();

    expect(screen.getByLabelText("Address")).toHaveAccessibleDescription(
      "A local model runs on this computer: localhost or 127.0.0.1.",
    );
    expect(screen.getByLabelText("Model")).toHaveAccessibleDescription(
      "Enter the model's name.",
    );
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription(
      "Give the set-up a name.",
    );
    expect(requestHostPermission).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("refuses a name another set-up has", async () => {
    const { onSave } = renderForm({ choices: CHOICES });
    await fill("Name", "haiku");

    await save();

    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription(
      "Another set-up has that name.",
    );
    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves, and says what is missing, when access is refused", async () => {
    const { onSave, onDone } = renderForm({ granted: false });
    await pick("llama");

    await save();

    expect(onSave).toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledWith({
      name: "llama.cpp",
      refused: "http://localhost:8081",
    });
  });

  it("says when the set-up could not be saved, and stays open", async () => {
    const { onDone } = renderForm({
      saved: err({ kind: "write-failed", message: "storage is full" }),
    });

    await save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The set-up could not be saved: storage is full",
    );
    expect(onDone).not.toHaveBeenCalled();
  });

  it("can be left without saving", async () => {
    const { onCancel, onSave } = renderForm();

    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
});
