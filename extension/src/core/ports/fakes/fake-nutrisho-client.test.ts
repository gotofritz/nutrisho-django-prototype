import { describe, expect, it } from "vitest";

import { err, ok } from "../../result";
import { EMPTY_VOCABULARY } from "../../vocabulary";
import { createFakeNutrishoClient } from "./fake-nutrisho-client";

describe("createFakeNutrishoClient", () => {
  it("answers with an empty library for nobody to begin with", async () => {
    expect(await createFakeNutrishoClient().vocabulary()).toEqual(
      ok(EMPTY_VOCABULARY),
    );
  });

  it("answers with what it was told to, and counts the calls", async () => {
    const client = createFakeNutrishoClient();
    const lists = { ...EMPTY_VOCABULARY, user: "cook", tags: ["dinner"] };

    client.answerVocabulary(ok(lists));

    expect(await client.vocabulary()).toEqual(ok(lists));
    expect(client.calls).toBe(1);
  });

  it("can fail the way the real one does", async () => {
    const client = createFakeNutrishoClient();
    const refusal = err({
      kind: "unauthorised" as const,
      message: "Send a valid API token",
    });

    client.answerVocabulary(refusal);

    expect(await client.vocabulary()).toEqual(refusal);
  });
});
