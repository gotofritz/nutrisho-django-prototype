import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { build } from "wxt";
import { beforeAll, describe, expect, it } from "vitest";

// Against the artefact that ships: what WXT emits for each browser. M6 adds
// the permissions and pins them here too (plan 012, D14).
type Manifest = {
  manifest_version?: number;
  name?: string;
  description?: string;
  permissions?: string[];
  host_permissions?: string[];
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

  it("asks for no host permission yet", () => {
    expect(built[browser]!.host_permissions ?? []).toEqual([]);
  });
});

it("opens the sidebar on Firefox", () => {
  expect(built.firefox!.sidebar_action?.default_panel).toBe("sidepanel.html");
});

it("opens the side panel on Chrome", () => {
  expect(built.chrome!.side_panel?.default_path).toBe("sidepanel.html");
});
