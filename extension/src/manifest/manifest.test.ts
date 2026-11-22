import { describe, expect, it } from "vitest";

import {
  CAPTURE_COMMAND,
  GECKO_ID,
  LOOPBACK_HOSTS,
  REMOTE_HOST,
  manifestExtras,
} from "./manifest";

// Plan 012, D14: the permission ceiling is a constraint, not a default.
// Whole-object equality on purpose: widening the manifest has to break a test
// rather than slip through a diff.
describe("manifest permissions", () => {
  it.each(["firefox", "chrome"])(
    "declares exactly the ceiling on %s",
    (target) => {
      // The sidebar's own permission is not here: WXT adds it on Chrome from
      // the sidepanel entrypoint, and the generated-manifest test holds it.
      expect(manifestExtras(target).permissions).toEqual([
        "activeTab",
        "contextMenus",
        "scripting",
        "storage",
      ]);
    },
  );

  it.each(["firefox", "chrome"])(
    "is granted no host at install on %s",
    (target) => {
      expect(manifestExtras(target).host_permissions).toEqual([]);
    },
  );

  // The server's address is a setting (D17), so its host is an optional
  // permission, asked for when it is saved. Loopback, and nutrisho.com over
  // https (M12, Advanced Mode).
  it.each(["firefox", "chrome"])(
    "offers %s loopback and nutrisho.com and nothing else as optional hosts",
    (target) => {
      expect(manifestExtras(target).optional_host_permissions).toEqual([
        "http://localhost/*",
        "http://127.0.0.1/*",
        "https://nutrisho.com/*",
      ]);
    },
  );

  it("offers one optional host for each name the settings accept", () => {
    expect(manifestExtras("firefox").optional_host_permissions).toEqual([
      ...LOOPBACK_HOSTS.map((host) => `http://${host}/*`),
      `https://${REMOTE_HOST}/*`,
    ]);
  });

  it("never asks for every site", () => {
    for (const target of ["firefox", "chrome"]) {
      const extras = manifestExtras(target);
      expect([
        ...extras.permissions,
        ...extras.host_permissions,
        ...extras.optional_host_permissions,
      ]).not.toContain("<all_urls>");
    }
  });
});

describe("manifest identity", () => {
  // Pinned so the extension keeps its storage, and the permissions granted
  // to it, across a reload and an update.
  it("pins the Firefox extension id", () => {
    expect(manifestExtras("firefox").browser_specific_settings?.gecko.id).toBe(
      GECKO_ID,
    );
    expect(GECKO_ID).toBe("nutrisho-clipper@gotofritz.net");
  });

  it("declares no data collection, as AMO requires of a new extension", () => {
    expect(
      manifestExtras("firefox").browser_specific_settings?.gecko
        .data_collection_permissions,
    ).toEqual({ required: ["none"] });
  });

  it("does not emit Firefox settings on Chrome", () => {
    expect(manifestExtras("chrome").browser_specific_settings).toBeUndefined();
  });

  // Plan 012, M6: anklipper pins a Chrome `key` for AnkiConnect's origin
  // allowlist. Nutrisho signs a request in with its API key, not its origin.
  it.each(["firefox", "chrome"])("pins no Chrome key on %s", (target) => {
    expect(manifestExtras(target)).not.toHaveProperty("key");
  });
});

// `commands` and `action` are manifest keys, not permissions, so they widen
// nothing; the names have to match the ones the background listens for.
describe("manifest gestures", () => {
  it.each(["firefox", "chrome"])("declares one shortcut on %s", (target) => {
    expect(Object.keys(manifestExtras(target).commands)).toEqual([
      CAPTURE_COMMAND,
    ]);
  });

  it("suggests a shortcut neither browser has already taken", () => {
    const command = manifestExtras("firefox").commands[CAPTURE_COMMAND];

    expect(command?.suggested_key?.default).toBe("Alt+Shift+N");
    expect(command?.description).toBe("Clip the selected text into Nutrisho");
  });

  it.each(["firefox", "chrome"])(
    "puts a button in the toolbar on %s",
    (target) => {
      expect(manifestExtras(target).action).toEqual({
        default_title: "Clip into Nutrisho",
      });
    },
  );
});
