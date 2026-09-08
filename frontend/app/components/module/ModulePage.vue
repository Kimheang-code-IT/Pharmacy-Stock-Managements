<script setup lang="ts">
import { useModuleRoute } from '~/composables/module/useModule'

const { module } = useModuleRoute()
</script>
<template>
  <div class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
    <ModuleDocumentView v-if="module" />
    <div v-else class="grid h-full min-h-0 flex-1 place-items-center p-8">
      <UEmpty
        variant="naked"
        icon="i-lucide-unplug"
        title="This page is not wired yet"
        description="The workspace could not resolve a module for this route."
      />
    </div>
  </div>
</template>
