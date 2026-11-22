import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { build } from "wxt";
import { beforeAll, describe, expect, it } from "vitest";

import { CONTENT_SCRIPT_FILE } from "@/platform/scripting";

// Against the artefact that ships: what WXT emits for each browser. The unit
// test beside `manifestExtras` covers what this project declares; this one
// covers what WXT adds on top, such as Chrome's `sidePanel` permission. A
// permission can be widened from either side, so both are pinned (D14).
type Manifest = {
  manifest_version?: number;
  name?: string;
  description?: string;
  permissions?: string[];
  host_permissions?: string[];
  optional_host_permissions?: string[];
  browser_specific_settings?: { gecko?: { id?: string } };
  key?: string;
  action?: { default_title?: string };
  commands?: Record<string, unknown>;
  content_scripts?: unknown;
  options_ui?: { page?: string; open_in_tab?: boolean };
  sidebar_action?: { default_panel?: string };
  side_panel?: { default_path?: string };
};

const built: Record<string, Manifest> = {};

/** The one place the description is written. Read, never retyped. */
const pkg = JSON.parse(readFileSync(resolve("package.json"), "utf8")) as {
  description: string;
};

beforeAll(async () => {
  for (const browser of ["firefox", "chrome"]) {
    const output = await build({ browser, mode: "production" });
    built[browser] = output.manifest as Manifest;
  }
}, 120_000);

describe.each(["firefox", "chrome"])("the %s build", (browser) => {
  it("is a Manifest V3 extension named for Nutrisho", () => {
    const manifest = built[browser]!;
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.name).toBe("Nutrisho clipper");
    expect(manifest.description).toBe(pkg.description);
  });

  it("asks for no host at install", () => {
    expect(built[browser]!.host_permissions ?? []).toEqual([]);
  });

  // The server's address is asked for when it is saved, and only loopback
  // can be asked for at all, so no setting points the clipper off the machine.
  it("offers loopback, and nothing else, as an optional host", () => {
    expect(built[browser]!.optional_host_permissions).toEqual([
      "http://localhost/*",
      "http://127.0.0.1/*",
    ]);
  });

  // A declared content script needs match patterns, and those are
  // install-time host permissions the ceiling does not allow.
  it("declares no content script", () => {
    expect(built[browser]!.content_scripts).toBeUndefined();
  });

  // Injected on the gesture by file path. A path that drifts fails only on a
  // real page, so it is checked against the build.
  it("emits the content script where injection asks for it", () => {
    expect(
      existsSync(resolve(`.output/${browser}-mv3${CONTENT_SCRIPT_FILE}`)),
    ).toBe(true);
  });

  it("declares the one shortcut", () => {
    expect(Object.keys(built[browser]!.commands ?? {})).toEqual([
      "clip-recipe",
    ]);
  });

  it("puts a clip button on the toolbar", () => {
    expect(built[browser]!.action?.default_title).toBe("Clip into Nutrisho");
  });

  it("has an options page that opens in a tab", () => {
    expect(built[browser]!.options_ui?.page).toBe("options.html");
    expect(built[browser]!.options_ui?.open_in_tab).toBe(true);
  });

  // The server allows a key, not an origin, so nothing needs a stable Chrome
  // id: no `key`, and no private key to keep.
  it("carries no Chrome key", () => {
    expect(built[browser]!.key).toBeUndefined();
  });
});

it("ships exactly the permission ceiling on Firefox", () => {
  expect(built.firefox!.permissions).toEqual([
    "activeTab",
    "contextMenus",
    "scripting",
    "storage",
  ]);
});

it("ships the ceiling plus Chrome's own side panel permission", () => {
  expect(built.chrome!.permissions?.slice().sort()).toEqual([
    "activeTab",
    "contextMenus",
    "scripting",
    "sidePanel",
    "storage",
  ]);
});

it("pins the Firefox extension id", () => {
  expect(built.firefox!.browser_specific_settings?.gecko?.id).toBe(
    "nutrisho-clipper@gotofritz.net",
  );
});

it("opens the sidebar on Firefox", () => {
  expect(built.firefox!.sidebar_action?.default_panel).toBe("sidepanel.html");
});

it("opens the side panel on Chrome", () => {
  expect(built.chrome!.side_panel?.default_path).toBe("sidepanel.html");
});
