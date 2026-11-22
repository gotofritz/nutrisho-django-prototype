import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { BUILT_IN, defaultsFor } from "@/core/model-settings";
import {
  createFakeModelSettingsStore,
  type FakeModelSettingsStore,
} from "@/core/ports/fakes/fake-model-settings-store";

import ModelForm from "./ModelForm.svelte";

const KEY = "sk-ant-api03-clipper";

function renderForm(
  store: FakeModelSettingsStore = createFakeModelSettingsStore(),
  granted = true,
) {
  const requestHostPermission = vi.fn<(pattern: string) => Promise<boolean>>(
    async () => granted,
  );
  render(ModelForm, { store, requestHostPermission });
  return { store, requestHostPermission };
}

async function pick(label: string) {
  await fireEvent.change(
    await screen.findByRole("combobox", { name: "Line scanner" }),
    { target: { value: label } },
  );
}

async function fill(label: string, value: string) {
  await fireEvent.input(screen.getByLabelText(label), { target: { value } });
}

async function save() {
  await fireEvent.click(
    screen.getByRole("button", { name: "Save the line scanner" }),
  );
}

async function stored(store: FakeModelSettingsStore) {
  const loaded = await store.load();
  return loaded.ok ? loaded.value : undefined;
}

// Plan 012, M13 (#181): the user's own model is set up on the options page.
describe("the line scanner form", () => {
  it("starts from the built-in scan, asking for nothing more", async () => {
    renderForm();

    expect(
      await screen.findByRole("combobox", { name: "Line scanner" }),
    ).toHaveValue("built-in");
    expect(screen.queryByLabelText("Address")).toBeNull();
    expect(screen.queryByLabelText("Model")).toBeNull();
  });

  it("fills in where timbuktu's guide starts a backend", async () => {
    renderForm();

    await pick("llama");

    expect(screen.getByLabelText("Address")).toHaveValue(
      "http://localhost:8081",
    );
    expect(screen.getByLabelText("Model")).toHaveValue("");
    expect(screen.getByLabelText("Server key")).toHaveValue("");
  });

  it("asks for the model's host first, then saves", async () => {
    const { store, requestHostPermission } = renderForm();
    await pick("mlx");
    await fill("Address", "http://127.0.0.1:8080/");

    await save();

    expect(await screen.findByText("Saved.")).toBeVisible();
    expect(requestHostPermission).toHaveBeenCalledWith("http://127.0.0.1/*");
    expect(await stored(store)).toEqual({
      ...defaultsFor("mlx"),
      address: "http://127.0.0.1:8080",
    });
  });

  it("starts from what was saved", async () => {
    renderForm(createFakeModelSettingsStore(defaultsFor("llama")));

    expect(
      await screen.findByDisplayValue("http://localhost:8081"),
    ).toBeVisible();
  });

  it("sets Anthropic up with your key, and no address to type", async () => {
    const { store, requestHostPermission } = renderForm();
    await pick("anthropic");

    expect(screen.queryByLabelText("Address")).toBeNull();
    expect(screen.queryByLabelText("Server key")).toBeNull();
    expect(screen.getByLabelText("Anthropic key")).toHaveAccessibleDescription(
      /a key for the clipper alone, with a low spending limit/,
    );
    await fill("Anthropic key", KEY);
    await save();

    await screen.findByText("Saved.");
    expect(requestHostPermission).toHaveBeenCalledWith(
      "https://api.anthropic.com/*",
    );
    expect(await stored(store)).toEqual({
      ...defaultsFor("anthropic"),
      key: KEY,
    });
    // D11: a saved key is never shown again.
    expect(screen.getByLabelText("Anthropic key")).toHaveValue("");
  });

  it("keeps the saved key when the field is left empty", async () => {
    const store = createFakeModelSettingsStore({
      ...defaultsFor("anthropic"),
      key: KEY,
    });
    renderForm(store);
    expect(
      await screen.findByText(/A key is saved\. Leave this empty to keep it/),
    ).toBeVisible();
    expect(screen.getByLabelText("Anthropic key")).toHaveValue("");

    await save();

    await screen.findByText("Saved.");
    expect((await stored(store))?.key).toBe(KEY);
  });

  it("does not carry a key over to another backend", async () => {
    const store = createFakeModelSettingsStore({
      ...defaultsFor("anthropic"),
      key: KEY,
    });
    renderForm(store);
    await screen.findByText(/A key is saved/);
    await pick("llama");

    await save();

    await screen.findByText("Saved.");
    expect((await stored(store))?.key).toBe("");
  });

  it("says when the Anthropic key is missing", async () => {
    renderForm();
    await pick("anthropic");

    await save();

    expect(screen.getByLabelText("Anthropic key")).toHaveAccessibleDescription(
      "Enter your Anthropic key.",
    );
  });

  it("names what is wrong at its field, and saves nothing", async () => {
    const { store, requestHostPermission } = renderForm();
    await pick("mlx");
    await fill("Address", "http://192.168.1.5:8080");
    await fill("Model", "");

    await save();

    expect(screen.getByLabelText("Address")).toHaveAccessibleDescription(
      "A local model runs on this computer: localhost or 127.0.0.1.",
    );
    expect(screen.getByLabelText("Model")).toHaveAccessibleDescription(
      "Enter the model's name.",
    );
    expect(requestHostPermission).not.toHaveBeenCalled();
    expect(await stored(store)).toEqual(BUILT_IN);
  });

  it("goes back to the built-in scan without asking for anything", async () => {
    const { store, requestHostPermission } = renderForm(
      createFakeModelSettingsStore(defaultsFor("mlx")),
    );
    await screen.findByDisplayValue("http://localhost:8080");
    await pick("built-in");

    await save();

    await screen.findByText("Saved.");
    expect(requestHostPermission).not.toHaveBeenCalled();
    expect(await stored(store)).toEqual(BUILT_IN);
  });

  it("saves, and says what is missing, when access is refused", async () => {
    const { store } = renderForm(createFakeModelSettingsStore(), false);
    await pick("llama");

    await save();

    expect(
      await screen.findByText(
        /was not allowed to reach http:\/\/localhost:8081/,
      ),
    ).toBeVisible();
    expect((await stored(store))?.backend).toBe("llama");
  });

  it("says when the choice could not be saved", async () => {
    const store = createFakeModelSettingsStore();
    renderForm(store);
    await pick("llama");
    store.failWith({ kind: "write-failed", message: "storage is full" });

    await save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The line scanner could not be saved: storage is full",
    );
  });
});
