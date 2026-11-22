import { LOOPBACK_HOSTS } from "@/manifest/manifest";

import { err, ok, type Result } from "./result";

/**
 * What the user configures on the options page (plan 012, M6): where their
 * Nutrisho is, and the API key that signs the clipper in (D11).
 */
export interface Settings {
  /** An origin: scheme, host and port, with no path. */
  readonly serverUrl: string;
  /** `nsh_` and the rest, from `create_api_token`; "" until one is saved. */
  readonly apiKey: string;
}

/** `make dev`'s address (D17). */
export const DEFAULT_SETTINGS: Settings = {
  serverUrl: "http://localhost:8987",
  apiKey: "",
};

export type SettingsField = keyof Settings;

export type SettingsIssueCode =
  | "missing"
  | "not-a-url"
  /** Only `http`: the dev server on loopback serves nothing else (D17). */
  | "not-http"
  /** Only this machine, until there is a production server (#87). */
  | "not-loopback"
  | "not-a-key";

export interface SettingsIssue {
  readonly field: SettingsField;
  readonly code: SettingsIssueCode;
  readonly message: string;
}

const LOOPBACK: readonly string[] = LOOPBACK_HOSTS;

/** `nsh_` and the URL-safe characters `secrets.token_urlsafe` uses. */
const KEY = /^nsh_[A-Za-z0-9_-]+$/;

function issue(
  field: SettingsField,
  code: SettingsIssueCode,
  message: string,
): SettingsIssue {
  return { field, code, message };
}

function checkServerUrl(input: string): Result<string, SettingsIssue> {
  const typed = input.trim();
  if (typed === "") {
    return err(issue("serverUrl", "missing", "Enter your Nutrisho's address."));
  }

  // `new URL("localhost:8987")` parses, as the scheme `localhost:`, so an
  // address with no `://` is not one.
  let url: URL;
  try {
    if (!typed.includes("://")) throw new TypeError("no scheme");
    url = new URL(typed);
  } catch {
    return err(
      issue(
        "serverUrl",
        "not-a-url",
        "Enter a whole address, such as http://localhost:8987.",
      ),
    );
  }
  if (url.protocol !== "http:") {
    return err(
      issue("serverUrl", "not-http", "The address has to start with http://."),
    );
  }
  if (!LOOPBACK.includes(url.hostname)) {
    return err(
      issue(
        "serverUrl",
        "not-loopback",
        "For now the clipper only talks to a Nutrisho on this computer: localhost or 127.0.0.1.",
      ),
    );
  }
  return ok(url.origin);
}

function checkApiKey(input: string): Result<string, SettingsIssue> {
  const typed = input.trim();
  if (typed === "") {
    return err(issue("apiKey", "missing", "Enter an API key."));
  }
  if (!KEY.test(typed)) {
    return err(
      issue(
        "apiKey",
        "not-a-key",
        "That is not an API key: a key starts with nsh_ and has no spaces.",
      ),
    );
  }
  return ok(typed);
}

/** What the user typed, checked and tidied; every problem at once. */
export function checkSettings(input: {
  readonly serverUrl: string;
  readonly apiKey: string;
}): Result<Settings, readonly SettingsIssue[]> {
  const serverUrl = checkServerUrl(input.serverUrl);
  const apiKey = checkApiKey(input.apiKey);
  const issues = [serverUrl, apiKey].flatMap((checked) =>
    checked.ok ? [] : [checked.error],
  );

  return serverUrl.ok && apiKey.ok
    ? ok({ serverUrl: serverUrl.value, apiKey: apiKey.value })
    : err(issues);
}

/**
 * Whatever is stored, as settings. A value that does not check degrades to its
 * own default, and never fails the read: an extension that will not start
 * because of its own storage is worse than one that asks for its settings
 * again.
 */
export function readSettings(stored: unknown): Settings {
  const raw =
    typeof stored === "object" && stored !== null
      ? (stored as Record<string, unknown>)
      : {};
  const serverUrl =
    typeof raw.serverUrl === "string" ? checkServerUrl(raw.serverUrl) : null;
  const apiKey =
    typeof raw.apiKey === "string" ? checkApiKey(raw.apiKey) : null;

  return {
    serverUrl: serverUrl?.ok ? serverUrl.value : DEFAULT_SETTINGS.serverUrl,
    apiKey: apiKey?.ok ? apiKey.value : DEFAULT_SETTINGS.apiKey,
  };
}

/**
 * The host permission an address needs. Without the port: MDN says Firefox's
 * match patterns take none, so `http://localhost/*` covers every port on it.
 */
export function hostPatternFor(serverUrl: string): string {
  const url = new URL(serverUrl);
  return `${url.protocol}//${url.hostname}/*`;
}

/**
 * The server's page where a user makes their own API key (#150), on an
 * address the settings would take; undefined for any other.
 */
export function keysPageFor(serverUrl: string): string | undefined {
  const checked = checkServerUrl(serverUrl);
  return checked.ok ? `${checked.value}/recipes/keys/` : undefined;
}
