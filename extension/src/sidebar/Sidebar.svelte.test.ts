import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import Sidebar from "./Sidebar.svelte";

describe("Sidebar", () => {
  it("names the extension", () => {
    render(Sidebar);
    expect(
      screen.getByRole("heading", { name: "Nutrisho clipper" }),
    ).toBeInTheDocument();
  });

  it("says nothing is clipped yet", () => {
    render(Sidebar);
    expect(screen.getByText("Nothing clipped yet.")).toBeInTheDocument();
  });
});
