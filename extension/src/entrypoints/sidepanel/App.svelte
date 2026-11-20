<script lang="ts">
  import { createNutrishoClient } from "@/nutrisho/client";
  import {
    createStoredClipping,
    watchClipping,
  } from "@/platform/clipping-store";
  import { createOptionsPage } from "@/platform/options";
  import { createPermissions, hostPermissionFor } from "@/platform/permissions";
  import {
    createStoredSettings,
    loadSettingsOrDefaults,
  } from "@/platform/settings-store";
  import { createStorage } from "@/platform/storage";
  import Sidebar from "@/sidebar/Sidebar.svelte";

  // A shell: it builds the adapters and hands them to the sidebar, which is
  // where the tested behaviour is.
  const storage = createStorage();
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
  clippings={createStoredClipping(storage)}
  subscribe={(onChange) => watchClipping(storage, onChange)}
  {client}
  openSettings={() => void options.open()}
/>
