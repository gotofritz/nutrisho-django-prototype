<script lang="ts">
  import SettingsForm from "@/options/SettingsForm.svelte";
  import { createPermissions } from "@/platform/permissions";
  import { createStoredSettings } from "@/platform/settings-store";
  import { createStorage } from "@/platform/storage";

  // A shell, like the sidebar's: it builds the adapters and hands them to the
  // form, which is where the tested behaviour is.
  const permissions = createPermissions();
  const settings = createStoredSettings(createStorage());
</script>

<!--
  The permission request is passed rather than made here: it has to happen in
  the same task as the Save press, and the form is what has the press.
-->
<SettingsForm
  {settings}
  requestHostPermission={(pattern) =>
    permissions.request({ origins: [pattern] })}
/>
