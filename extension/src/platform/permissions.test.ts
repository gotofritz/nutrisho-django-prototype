import { browser, type Browser } from "wxt/browser";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPermissions, hostPermissionFor } from "./permissions";

// The fake browser leaves `permissions` unimplemented, so the two calls this
// wrapper makes are stubbed.
type Check = (request: Browser.permissions.Permissions) => Promise<boolean>;

const contains = vi.fn<Check>();
const requestPermission = vi.fn<Check>();

beforeEach(() => {
  contains.mockReset();
  requestPermission.mockReset();
  browser.permissions.contains =
    contains as unknown as typeof browser.permissions.contains;
  browser.permissions.request =
    requestPermission as unknown as typeof browser.permissions.request;
});

const DEV_SERVER = hostPermissionFor("http://localhost:8987");

describe("permissions", () => {
  // Firefox MV3 grants no host at install, so the extension finds out at
  // runtime rather than in a failed request later.
  it("reports the server's host as missing when it is not granted", async () => {
    contains.mockResolvedValue(false);

    await expect(createPermissions().has(DEV_SERVER)).resolves.toBe(false);
    expect(contains).toHaveBeenCalledWith({ origins: ["http://localhost/*"] });
  });

  it("reports it as present once it is granted", async () => {
    contains.mockResolvedValue(true);

    await expect(createPermissions().has(DEV_SERVER)).resolves.toBe(true);
  });

  it("asks for exactly the permission it was given, and reports the answer", async () => {
    requestPermission.mockResolvedValue(true);

    await expect(createPermissions().request(DEV_SERVER)).resolves.toBe(true);
    expect(requestPermission).toHaveBeenCalledWith({
      origins: ["http://localhost/*"],
    });
  });

  it("reports a refused request as false rather than throwing", async () => {
    requestPermission.mockResolvedValue(false);

    await expect(createPermissions().request(DEV_SERVER)).resolves.toBe(false);
  });

  // Firefox rejects `permissions.request` outside a user gesture. That is a
  // refusal, not a crash: the caller retries from a button.
  it("reports a request made outside a user gesture as false", async () => {
    requestPermission.mockRejectedValue(
      new Error(
        "permissions.request may only be called from a user input handler",
      ),
    );

    await expect(createPermissions().request(DEV_SERVER)).resolves.toBe(false);
  });
});

describe("hostPermissionFor", () => {
  // Plan 012, M6: anklipper's kept the port. MDN says Firefox's match patterns
  // take none, so the host alone is asked for, as the manifest offers it.
  it("asks for the server's host, without its port", () => {
    expect(hostPermissionFor("http://127.0.0.1:8000")).toEqual({
      origins: ["http://127.0.0.1/*"],
    });
  });
});
