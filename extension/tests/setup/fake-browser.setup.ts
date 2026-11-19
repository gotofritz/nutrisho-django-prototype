import { fakeBrowser } from "wxt/testing/fake-browser";
import { beforeEach } from "vitest";

// The fake browser keeps its state in module scope, so storage written by one
// test leaks into the next. Leaked storage is the standard way an extension
// suite goes quietly wrong; reset before every case.
beforeEach(() => {
  fakeBrowser.reset();
});
