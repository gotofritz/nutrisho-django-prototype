import { screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_SCENE, SCENES } from "../../preview/scenes";

/**
 * The look preview (plan 012, M12) mounts each state of the clipper on the
 * fakes. Mounting each one here keeps the preview from rotting as the
 * components change.
 */
describe("the look preview", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("opens on a scene it has", () => {
    expect(SCENES[DEFAULT_SCENE]).toBeDefined();
  });

  it.each(Object.entries(SCENES))("mounts %s", async (_, scene) => {
    const target = document.createElement("div");
    document.body.append(target);

    scene.mount(target);

    expect(await screen.findAllByRole("heading")).not.toHaveLength(0);
  });
});
