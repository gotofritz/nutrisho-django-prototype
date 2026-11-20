import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import {
  createFakeSettingsStore,
  type FakeSettingsStore,
} from "@/core/ports/fakes/fake-settings-store";
import { DEFAULT_SETTINGS } from "@/core/settings";

import SettingsForm from "./SettingsForm.svelte";

const KEY = "nsh_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";

function renderForm(
  settings: FakeSettingsStore = createFakeSettingsStore(),
  requestHostPermission = vi.fn<(pattern: string) => Promise<boolean>>(
    async () => true,
  ),
) {
  return {
    settings,
    requestHostPermission,
    ...render(SettingsForm, { settings, requestHostPermission }),
  };
}

async function fill(label: string, value: string) {
  await fireEvent.input(await screen.findByLabelText(label), {
    target: { value },
  });
}

async function save() {
  await fireEvent.click(screen.getByRole("button", { name: "Save" }));
}

describe("the settings form", () => {
  it("labels both controls", async () => {
    renderForm();

    expect(
      await screen.findByLabelText("Your Nutrisho's address"),
    ).toBeVisible();
    expect(screen.getByLabelText("API key")).toBeVisible();
  });

  it("starts from the saved address", async () => {
    renderForm(
      createFakeSettingsStore({
        serverUrl: "http://127.0.0.1:8000",
        apiKey: KEY,
      }),
    );

    expect(
      await screen.findByDisplayValue("http://127.0.0.1:8000"),
    ).toBeVisible();
  });

  // Plan 012, D11: the key is never shown again.
  it("never shows a saved key, only that there is one", async () => {
    renderForm(
      createFakeSettingsStore({
        serverUrl: DEFAULT_SETTINGS.serverUrl,
        apiKey: KEY,
      }),
    );

    expect(await screen.findByText(/A key is saved/)).toBeVisible();
    expect(screen.getByLabelText<HTMLInputElement>("API key").value).toBe("");
    expect(screen.getByLabelText("API key")).toHaveAttribute(
      "type",
      "password",
    );
  });

  it("saves the address and the key", async () => {
    const { settings } = renderForm();

    await fill("Your Nutrisho's address", "http://127.0.0.1:8000");
    await fill("API key", KEY);
    await save();

    expect(await screen.findByText("Saved.")).toBeVisible();
    expect(await settings.load()).toEqual({
      ok: true,
      value: { serverUrl: "http://127.0.0.1:8000", apiKey: KEY },
    });
  });

  it("keeps the saved key when the field is left empty", async () => {
    const { settings } = renderForm(
      createFakeSettingsStore({
        serverUrl: DEFAULT_SETTINGS.serverUrl,
        apiKey: KEY,
      }),
    );

    await fill("Your Nutrisho's address", "http://127.0.0.1:8000");
    await save();

    await screen.findByText("Saved.");
    expect(await settings.load()).toEqual({
      ok: true,
      value: { serverUrl: "http://127.0.0.1:8000", apiKey: KEY },
    });
  });

  // Firefox refuses a permission request made outside the gesture, so it is
  // asked for first, before anything is awaited, and for the host alone.
  it("asks for the server's host before it saves anything", async () => {
    const order: string[] = [];
    const settings = createFakeSettingsStore();
    const saveSettings = settings.save.bind(settings);
    settings.save = async (value) => {
      order.push("save");
      return saveSettings(value);
    };
    const { requestHostPermission } = renderForm(
      settings,
      vi.fn<(pattern: string) => Promise<boolean>>(async () => {
        order.push("permission");
        return true;
      }),
    );

    await fill("API key", KEY);
    await save();
    await screen.findByText("Saved.");

    expect(requestHostPermission).toHaveBeenCalledWith("http://localhost/*");
    expect(order).toEqual(["permission", "save"]);
  });

  it("saves, and says what is missing, when access is refused", async () => {
    const { settings } = renderForm(
      createFakeSettingsStore(),
      vi.fn(async () => false),
    );

    await fill("API key", KEY);
    await save();

    expect(
      await screen.findByText(
        /was not allowed to reach http:\/\/localhost:8987/,
      ),
    ).toBeVisible();
    const saved = await settings.load();
    expect(saved.ok && saved.value.apiKey).toBe(KEY);
  });

  it("names what is wrong with each field, and saves nothing", async () => {
    const { settings, requestHostPermission } = renderForm();

    await fill("Your Nutrisho's address", "https://recipes.example.com");
    await fill("API key", "not a key");
    await save();

    const address = screen.getByLabelText("Your Nutrisho's address");
    expect(address).toHaveAttribute("aria-invalid", "true");
    expect(address).toHaveAccessibleDescription(/http:\/\//);
    expect(screen.getByLabelText("API key")).toHaveAccessibleDescription(
      /starts with nsh_/,
    );
    expect(requestHostPermission).not.toHaveBeenCalled();
    expect(await settings.load()).toEqual({
      ok: true,
      value: DEFAULT_SETTINGS,
    });
  });

  it("says when the settings could not be read, and starts from the defaults", async () => {
    const settings = createFakeSettingsStore();
    settings.failWith({ kind: "read-failed", message: "storage is gone" });

    renderForm(settings);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not be read",
    );
    expect(
      screen.getByLabelText<HTMLInputElement>("Your Nutrisho's address").value,
    ).toBe(DEFAULT_SETTINGS.serverUrl);
  });

  it("says when the settings could not be saved", async () => {
    const settings = createFakeSettingsStore();
    renderForm(settings);
    await fill("API key", KEY);
    settings.failWith({ kind: "write-failed", message: "quota exceeded" });

    await save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not be saved: quota exceeded",
    );
  });
});
