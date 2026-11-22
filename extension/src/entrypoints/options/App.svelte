<script lang="ts">
  import SettingsForm from "@/options/SettingsForm.svelte";
  import { createPermissions } from "@/platform/permissions";
  import { createStoredSettings } from "@/platform/settings-store";
  import { createStorage } from "@/platform/storage";

  // A shell, like the sidebar's: it builds the adapters and hands them to the
  // form, which is where the tested behaviour is.
  const permissions = createPermissions();
  const storage = createStorage();
  const settings = createStoredSettings(storage);
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
<!-- The user's own models moved to the sidebar's Advanced Mode (#183). -->
<p class="moved">
  Your own models, for splitting lines and rewriting steps, are set up in the
  sidebar, under Advanced Mode.
</p>

<style>
  .moved {
    max-width: 36rem;
    margin: 1.5rem;
  }
</style>
