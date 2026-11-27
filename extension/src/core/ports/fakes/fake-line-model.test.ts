import { describe, expect, it } from "vitest";

import { err, ok } from "../../result";
import { createFakeLineModel } from "./fake-line-model";

describe("createFakeLineModel", () => {
  it("is not set up to begin with", async () => {
    const model = createFakeLineModel();

    expect(await model.splitLines(["2 eggs"])).toEqual(
      err({ kind: "not-set-up", message: "no model is set up" }),
    );
  });

  it("answers with what it was told to, and keeps the lines it was sent", async () => {
    const model = createFakeLineModel();
    model.answer(ok({ rows: [{ quantity: "2", ingredient: "eggs" }] }));

    expect(await model.splitLines(["2 eggs"])).toEqual(
      ok({ rows: [{ quantity: "2", ingredient: "eggs" }] }),
    );
    expect(model.sent).toEqual([["2 eggs"]]);
  });

  it("keeps the steps it was sent, and answers them the same way", async () => {
    const model = createFakeLineModel();
    model.answer(ok({ steps: [{ title: "", text: "Fry" }] }));

    expect(await model.rewriteSteps([{ title: "", text: "Fry it" }])).toEqual(
      ok({ steps: [{ title: "", text: "Fry" }] }),
    );
    expect(model.stepsSent).toEqual([[{ title: "", text: "Fry it" }]]);
  });

  it("keeps the blurbs it was sent, and answers them the same way", async () => {
    const model = createFakeLineModel();
    model.answer(ok({ blurb: "A salad." }));

    expect(await model.rewriteBlurb("Una insalata.")).toEqual(
      ok({ blurb: "A salad." }),
    );
    expect(model.blurbsSent).toEqual(["Una insalata."]);
  });

  it("checks as it answers, and counts the checks", async () => {
    const model = createFakeLineModel();

    expect((await model.check()).ok).toBe(false);
    model.answer(ok({ rows: [] }));
    expect(await model.check()).toEqual(ok(undefined));
    expect(model.checks).toBe(2);
  });
});
