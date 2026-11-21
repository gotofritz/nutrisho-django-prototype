import type { CaptureReport } from "@/background/capture";
import { startBackground } from "@/background/start";
import { createAction } from "@/platform/action";
import { createStoredClipping } from "@/platform/clipping-store";
import { createCommands } from "@/platform/commands";
import { createContextMenus } from "@/platform/context-menus";
import { createRuntimeMessaging } from "@/platform/runtime-messaging";
import { createScripting } from "@/platform/scripting";
import { createBrowserSidebar } from "@/platform/sidebar";
import { createStorage } from "@/platform/storage";

// A shell. The background is an event page on Firefox and a service worker on
// Chrome, and both are unloaded when idle, so this runs on every wake-up and
// keeps no state of its own. Logic lives in `@/background/`, where tests reach
// it: the TDD hook exempts entrypoints.
export default defineBackground(() => {
  startBackground({
    messaging: createRuntimeMessaging(),
    menus: createContextMenus(),
    commands: createCommands(),
    action: createAction(),
    scripting: createScripting(),
    sidebar: createBrowserSidebar(),
    // Session storage: a new browser session starts without the last clipping.
    clippings: createStoredClipping(createStorage("session")),
    // What each capture did, in development only. The report carries kinds
    // and our own messages, never the page's text or address (D15), and the
    // DEV guard keeps it out of a release regardless.
    ...(import.meta.env.DEV
      ? {
          report: (report: CaptureReport) => {
            console[report.outcome === "failed" ? "warn" : "info"](
              "nutrisho clipper: capture",
              report,
            );
          },
        }
      : {}),
  });
});
