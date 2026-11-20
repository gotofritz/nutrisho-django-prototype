import { describe, expect, it, vi } from "vitest";

import { createSidebar, type SidebarBackings } from "./sidebar";

// The UI lives in the sidebar, and the two browsers spell it differently:
// Firefox has `sidebarAction`, Chrome has `sidePanel`. One interface covers
// both, and both are exercised here so the Chrome path cannot rot unnoticed.
function firefoxBackings(): SidebarBackings {
  return { sidebarAction: { open: vi.fn(async () => undefined) } };
}

function chromeBackings(): SidebarBackings {
  return { sidePanel: { open: vi.fn(async () => undefined) } };
}

describe.each([
  ["firefox sidebarAction", firefoxBackings],
  ["chrome sidePanel", chromeBackings],
])("sidebar on %s", (_label, backingsFor) => {
  it("opens", async () => {
    const backings = backingsFor();

    await expect(
      createSidebar(backings).open({ tabId: 7, windowId: 1 }),
    ).resolves.toEqual({ ok: true, value: undefined });
  });

  // Both browsers require the call inside the gesture's own task. An `await`
  // before it loses the gesture, so the wrapper must reach the API before it
  // yields; the capture depends on this.
  it("reaches the browser API before yielding to the event loop", () => {
    const backings = backingsFor();

    void createSidebar(backings).open({ tabId: 7, windowId: 1 });

    expect(
      backings.sidebarAction?.open ?? backings.sidePanel?.open,
    ).toHaveBeenCalled();
  });

  it("reports a refused open as a typed failure rather than an unhandled rejection", async () => {
    const backings = backingsFor();
    const open = backings.sidebarAction?.open ?? backings.sidePanel?.open;
    vi.mocked(open!).mockRejectedValue(
      new Error(
        "sidebarAction.open may only be called from a user input handler",
      ),
    );

    await expect(
      createSidebar(backings).open({ tabId: 7, windowId: 1 }),
    ).resolves.toEqual({
      ok: false,
      error: { kind: "open-failed", message: expect.any(String) },
    });
  });
});

describe("sidebar", () => {
  it("passes the gesture's tab to sidePanel, which is scoped to one", async () => {
    const backings = chromeBackings();

    await createSidebar(backings).open({ tabId: 7, windowId: 1 });

    expect(backings.sidePanel?.open).toHaveBeenCalledWith({ tabId: 7 });
  });

  it("falls back to the window when the gesture has no tab", async () => {
    const backings = chromeBackings();

    await createSidebar(backings).open({ windowId: 1 });

    expect(backings.sidePanel?.open).toHaveBeenCalledWith({ windowId: 1 });
  });

  // Firefox's sidebar is per window and takes no argument at all; promising
  // a per-tab sidebar on both would be promising behaviour only Chrome has.
  it("opens Firefox's window-scoped sidebar with no target", async () => {
    const backings = firefoxBackings();

    await createSidebar(backings).open({ tabId: 7, windowId: 1 });

    expect(backings.sidebarAction?.open).toHaveBeenCalledWith();
  });

  it("reports a sidePanel open with neither tab nor window as no-target", async () => {
    const backings = chromeBackings();

    await expect(createSidebar(backings).open({})).resolves.toEqual({
      ok: false,
      error: { kind: "no-target", message: expect.any(String) },
    });
    expect(backings.sidePanel?.open).not.toHaveBeenCalled();
  });

  it("reports a browser with neither API as unsupported", async () => {
    await expect(createSidebar({}).open({ tabId: 7 })).resolves.toEqual({
      ok: false,
      error: { kind: "unsupported", message: expect.any(String) },
    });
  });
});
