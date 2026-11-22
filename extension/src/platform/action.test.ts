import { browser } from "wxt/browser";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createAction } from "./action";

type ClickListener = (tab: { id?: number; url?: string }) => void;

let listeners: ClickListener[];

beforeEach(() => {
  listeners = [];
  browser.action = {
    onClicked: {
      addListener: vi.fn((listener: ClickListener) => {
        listeners.push(listener);
      }),
      removeListener: vi.fn((listener: ClickListener) => {
        listeners = listeners.filter((it) => it !== listener);
      }),
    },
  } as never;
});

describe("the toolbar button", () => {
  it("delivers a click as the tab it was made in", () => {
    const onClicked = vi.fn();
    createAction().onClicked(onClicked);

    listeners.forEach((listener) =>
      listener({ id: 7, url: "https://example.test/melanzane" }),
    );

    expect(onClicked).toHaveBeenCalledWith({
      tabId: 7,
      pageUrl: "https://example.test/melanzane",
    });
  });

  it("survives a click the browser reports with no tab", () => {
    const onClicked = vi.fn();
    createAction().onClicked(onClicked);

    listeners.forEach((listener) => listener({}));

    expect(onClicked).toHaveBeenCalledWith({});
  });

  it("stops delivering once the subscription is disposed", () => {
    const onClicked = vi.fn();

    createAction().onClicked(onClicked)();
    listeners.forEach((listener) => listener({ id: 7 }));

    expect(onClicked).not.toHaveBeenCalled();
  });
});
