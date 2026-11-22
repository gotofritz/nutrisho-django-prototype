import type { FetchLike } from "./client";

/**
 * Advanced Mode's log (plan 012, M12, #179): what went to the server and what
 * came back, a line each, as a browser's network panel shows it. Kept in
 * memory for the sidebar's life, never stored or sent. Neither the headers,
 * so never the key (D11), nor the bodies: only their sizes.
 */
export interface LogEntry {
  readonly at: Date;
  readonly text: string;
}

function size(bytes: number): string {
  return bytes < 1000 ? `${bytes} B` : `${(bytes / 1000).toFixed(1)} kB`;
}

function bytesOf(text: string): number {
  return new TextEncoder().encode(text).length;
}

/** `fetch`, noting each request and its reply or failure. */
export function loggedFetch(
  fetch: FetchLike,
  note: (entry: LogEntry) => void,
  now: () => Date = () => new Date(),
): FetchLike {
  return async (input, init) => {
    const method = init?.method ?? "GET";
    const sent = typeof init?.body === "string" ? init.body : undefined;
    const started = now();
    note({
      at: started,
      text: `→ ${method} ${input}${sent === undefined ? "" : ` · ${size(bytesOf(sent))}`}`,
    });
    const took = (at: Date) => `${at.getTime() - started.getTime()} ms`;
    try {
      const response = await fetch(input, init);
      // A copy is read for its size; the reply goes on unread.
      const body = await response.clone().text();
      const at = now();
      note({
        at,
        text: `← ${`${response.status} ${response.statusText}`.trim()} · ${size(bytesOf(body))} · ${took(at)}`,
      });
      return response;
    } catch (error) {
      const at = now();
      const reason =
        error instanceof Error
          ? `${error.name}: ${error.message}`
          : String(error);
      note({ at, text: `✕ ${reason} · ${took(at)}` });
      throw error;
    }
  };
}
