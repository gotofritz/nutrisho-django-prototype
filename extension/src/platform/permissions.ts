import { browser, type Browser } from "wxt/browser";

import { hostPatternFor } from "@/core/settings";

export interface PermissionRequest {
  readonly permissions?: readonly Browser.runtime.ManifestPermission[];
  readonly origins?: readonly string[];
}

/**
 * Optional-permission checks. Firefox MV3 grants no host permission at
 * install, so the extension asks at runtime, from the options page's Save;
 * Chrome answers `true` to the same call once the user has allowed it. One
 * code path, correct on both.
 */
export interface PermissionsPort {
  has(request: PermissionRequest): Promise<boolean>;
  /** Must be called synchronously from a user gesture, or Firefox refuses. */
  request(request: PermissionRequest): Promise<boolean>;
}

function toBrowserRequest(
  request: PermissionRequest,
): Browser.permissions.Permissions {
  return {
    ...(request.permissions ? { permissions: [...request.permissions] } : {}),
    ...(request.origins ? { origins: [...request.origins] } : {}),
  };
}

export function createPermissions(): PermissionsPort {
  return {
    async has(request: PermissionRequest): Promise<boolean> {
      return browser.permissions.contains(toBrowserRequest(request));
    },

    async request(request: PermissionRequest): Promise<boolean> {
      try {
        return await browser.permissions.request(toBrowserRequest(request));
      } catch {
        // Firefox rejects a request made outside a user input handler. That
        // is a refusal the caller retries from a button, not a crash.
        return false;
      }
    },
  };
}

/** The permission the server's address needs: its host, on any port. */
export function hostPermissionFor(serverUrl: string): PermissionRequest {
  return { origins: [hostPatternFor(serverUrl)] };
}
