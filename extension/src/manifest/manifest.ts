/**
 * The parts of the generated manifest that are ours (plan 012, D14).
 *
 * `wxt.config.ts` imports this, and `manifest.test.ts` pins it, so widening
 * the extension's permissions breaks a test rather than slipping through a
 * diff. Pure constants: nothing here may import `wxt/browser`, because WXT
 * loads this module at build time, outside any browser.
 */

/**
 * The hosts the server's address may name (D17). The address is a setting, so
 * its host is an **optional** permission: nothing is granted at install, and
 * the options page asks for the one the user typed, from the Save gesture.
 * `checkSettings` refuses any other host, so the setting and the permission
 * cannot disagree. Loopback is the dev server, over `http`; nutrisho.com is
 * the production server, over `https` only (M12, Advanced Mode).
 *
 * IPv6 is absent because match patterns have no syntax for a literal address.
 */
export const LOOPBACK_HOSTS = ["localhost", "127.0.0.1"] as const;

export const REMOTE_HOST = "nutrisho.com";

/** Where Anthropic's API is, for the user's own model (plan 012, M13). */
export const MODEL_HOST = "api.anthropic.com";

export const OPTIONAL_HOST_PERMISSIONS = [
  ...LOOPBACK_HOSTS.map((host) => `http://${host}/*`),
  `https://${REMOTE_HOST}/*`,
  `https://${MODEL_HOST}/*`,
];

/**
 * The permission ceiling (D14). Never `<all_urls>`: `activeTab` plus
 * `scripting` on a user gesture is enough to read a selection. Chrome's
 * `sidePanel` is absent on purpose: WXT derives it from the sidepanel
 * entrypoint, and `tests/manifest/generated-manifest.test.ts` holds the
 * emitted manifest to the ceiling.
 */
export const PERMISSIONS = [
  "activeTab",
  "contextMenus",
  "scripting",
  "storage",
] as const;

/**
 * Pinned, so the extension keeps its storage and the permissions granted to
 * it across a reload and an update.
 */
export const GECKO_ID = "nutrisho-clipper@gotofritz.net";
export const GECKO_MIN_VERSION = "128.0";

/**
 * The shortcut's name. The background listens for exactly this, so the two
 * live in one place. `Alt+Shift+N` is free on both browsers, where the
 * `Ctrl+Shift+` range is largely taken by their developer tools.
 */
export const CAPTURE_COMMAND = "clip-recipe";

/** The toolbar button's tooltip, and the menu entry's label. */
export const CAPTURE_TITLE = "Clip into Nutrisho";

export interface ManifestCommand {
  readonly suggested_key?: { readonly default: string };
  readonly description: string;
}

export interface GeckoSettings {
  readonly gecko: {
    readonly id: string;
    readonly strict_min_version: string;
    readonly data_collection_permissions: { readonly required: string[] };
  };
}

export interface ManifestExtras {
  readonly permissions: string[];
  readonly host_permissions: string[];
  readonly optional_host_permissions: string[];
  readonly commands: Readonly<Record<string, ManifestCommand>>;
  /** The toolbar button. No popup: a click opens the sidebar. */
  readonly action: { readonly default_title: string };
  readonly browser_specific_settings?: GeckoSettings;
}

export function manifestExtras(target: string): ManifestExtras {
  return {
    permissions: [...PERMISSIONS],
    host_permissions: [],
    optional_host_permissions: [...OPTIONAL_HOST_PERMISSIONS],
    commands: {
      [CAPTURE_COMMAND]: {
        suggested_key: { default: "Alt+Shift+N" },
        description: "Clip the selected text into Nutrisho",
      },
    },
    action: { default_title: CAPTURE_TITLE },
    ...(target === "firefox"
      ? {
          browser_specific_settings: {
            gecko: {
              id: GECKO_ID,
              strict_min_version: GECKO_MIN_VERSION,
              // Required by AMO for new extensions. Nothing leaves the
              // browser except a draft the user saves to their own server.
              data_collection_permissions: { required: ["none"] },
            },
          },
        }
      : {}),
  };
}
