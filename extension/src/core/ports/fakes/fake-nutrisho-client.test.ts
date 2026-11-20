import { describe, expect, it } from "vitest";

import { err, ok } from "../../result";
import { startDraft } from "../../recipe-draft";
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

describe("the fake's save", () => {
  const draft = startDraft({
    id: "01a1f5b5-dbe2-704a-b591-7ffbcff6762e",
    title: "Norma",
    url: "https://example.test/norma",
    now: "2026-11-20T09:30:00.000Z",
  });

  it("makes the recipe to begin with, and keeps what it was sent", async () => {
    const client = createFakeNutrishoClient();

    expect(await client.saveRecipe(draft)).toEqual(
      ok({
        openUrl: `http://localhost:8987/recipes/${draft.id}/?edit=1`,
        name: "Norma",
        created: true,
        renamed: false,
        inTrash: false,
        warnings: [],
      }),
    );
    expect(client.sent).toEqual([draft]);
  });

  it("answers with what it was told to", async () => {
    const client = createFakeNutrishoClient();
    const refusal = err({
      kind: "refused" as const,
      status: 400,
      message: "document.recipes[0].recipe_name is required.",
    });

    client.answerSave(refusal);

    expect(await client.saveRecipe(draft)).toEqual(refusal);
  });
});
