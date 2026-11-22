import { startContent } from "@/content/start";
import { createRuntimeMessaging } from "@/platform/runtime-messaging";

// A shell. Registered at runtime rather than in the manifest: a declared
// content script needs match patterns, and those become install-time host
// permissions the ceiling does not allow (D14). The background injects it
// through `activeTab` and `scripting`, on a user gesture.
export default defineContentScript({
  registration: "runtime",
  matches: [],
  main() {
    startContent({ messaging: createRuntimeMessaging() });
  },
});
