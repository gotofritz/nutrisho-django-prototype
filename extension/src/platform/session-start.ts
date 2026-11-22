import type { StoragePort } from "./storage";

/**
 * Whether the browser session has just begun (plan 012, M7). The drafts are
 * kept in local storage, across restarts, but a new session opens none of
 * them: session storage, emptied on every restart, holds the mark.
 */
export const SESSION_KEY = "session-started";

export interface SessionStart {
  /** True the first time it is asked in a browser session, false after. */
  isNew(): Promise<boolean>;
}

export function createSessionStart(session: StoragePort): SessionStart {
  return {
    async isNew(): Promise<boolean> {
      if ((await session.get<boolean>(SESSION_KEY)) === true) return false;
      await session.set(SESSION_KEY, true);
      return true;
    },
  };
}
