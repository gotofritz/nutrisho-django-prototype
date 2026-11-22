import { describe, expect, it } from "vitest";

import { createFakeStorage } from "./fakes/fake-storage";
import { SESSION_KEY, createSessionStart } from "./session-start";

// Drafts are kept in local storage, across restarts; a new browser session
// still starts with none open. Session storage is what tells one apart.
describe("the start of a browser session", () => {
  it("is the first time it is asked, and only that time", async () => {
    const session = createSessionStart(createFakeStorage());

    await expect(session.isNew()).resolves.toBe(true);
    await expect(session.isNew()).resolves.toBe(false);
  });

  it("is over once the session has been marked", async () => {
    const storage = createFakeStorage({ [SESSION_KEY]: true });

    await expect(createSessionStart(storage).isNew()).resolves.toBe(false);
  });
});
