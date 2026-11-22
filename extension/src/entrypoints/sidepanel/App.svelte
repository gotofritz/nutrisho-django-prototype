<script lang="ts">
  import { uuidV7 } from "@/core/uuid7";
  import { createNutrishoClient } from "@/nutrisho/client";
  import {
    createStoredClipping,
    watchClipping,
  } from "@/platform/clipping-store";
  import { createStoredDrafts } from "@/platform/draft-store";
  import { createOptionsPage } from "@/platform/options";
  import { createPermissions, hostPermissionFor } from "@/platform/permissions";
  import {
    createStoredSettings,
    loadSettingsOrDefaults,
  } from "@/platform/settings-store";
  import { createSessionStart } from "@/platform/session-start";
  import { createStorage } from "@/platform/storage";
  import Sidebar from "@/sidebar/Sidebar.svelte";

  // A shell: it builds the adapters and hands them to the sidebar, which is
  // where the tested behaviour is.
  const storage = createStorage();
  // The drafts are kept across restarts, in `storage.local` with the
  // settings; a new browser session opens none of them. The clipping is
  // kept only while the browser runs.
  const session = createStorage("session");
  const sessionStart = createSessionStart(session);
  const permissions = createPermissions();
  const options = createOptionsPage();
  const settings = createStoredSettings(storage);

  // The settings are read on every call, so a change on the options page
  // takes effect on the next Try again without reopening the sidebar. The
  // extension's own page calls the server, never a content script (D10).
  const client = createNutrishoClient({
    fetch: (input, init) => fetch(input, init),
    loadSettings: () => loadSettingsOrDefaults(settings),
    hasHostPermission: (serverUrl) =>
      permissions.has(hostPermissionFor(serverUrl)),
  });
</script>

<Sidebar
  clippings={createStoredClipping(session)}
  drafts={createStoredDrafts(storage)}
  newId={() => uuidV7(Date.now(), crypto.getRandomValues(new Uint8Array(10)))}
  subscribe={(onChange) => watchClipping(session, onChange)}
  {client}
  openSettings={() => void options.open()}
  isNewSession={() => sessionStart.isNew()}
/>
