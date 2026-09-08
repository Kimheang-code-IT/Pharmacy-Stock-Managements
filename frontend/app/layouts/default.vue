<script setup lang="ts">
import { useGlobalSearch } from '~/composables/search/useGlobalSearch'
import { useMenu } from '~/composables/layout/useMenu'
import { usePosChrome, isPosPath } from '~/composables/layout/usePosChrome'

const route = useRoute()
const { close } = useMenu()
const { isPosWorkspace, hidePosAppHeader, rememberAppPath } = usePosChrome()

watch(() => route.fullPath, (to, from) => {
  if (from) rememberAppPath(from)
  if (isPosPath(to.split('?')[0] || to)) close()
}, { immediate: true })

const { t } = useI18n()
const {
  open,
  searchTerm,
  mode,
  setMode,
  loading,
  asking,
  groups,
  placeholder,
  isHttpMode,
} = useGlobalSearch()
</script>

<template>
  <UDashboardGroup unit="rem" class="h-screen overflow-hidden bg-default">
    <LayoutAppSlidebar v-if="!isPosWorkspace" />

    <UDashboardSearch
      v-model:open="open"
      v-model:search-term="searchTerm"
      :groups="groups"
      :loading="loading || asking"
      :placeholder="placeholder"
      :color-mode="false"
      preserve-group-order
      :fuse="{
        // Nav filtering stays local; record hits use ignoreFilter (adapter-ranked)
        resultLimit: 48,
        fuseOptions: {
          ignoreLocation: true,
          threshold: 0.35,
          keys: ['label', 'description'],
        },
      }"
    >
      <template #footer>
        <div class="flex w-full flex-wrap items-center justify-between gap-2 border-t border-default px-3 py-2">
          <div class="flex items-center gap-1">
            <UButton
              size="xs"
              :color="mode === 'keyword' ? 'primary' : 'neutral'"
              :variant="mode === 'keyword' ? 'soft' : 'ghost'"
              icon="i-lucide-search"
              :label="t('core.search.modeKeyword')"
              @click="setMode('keyword')"
            />
            <!-- Semantic mode is a mock-only ranking feature; the connected
                 backend implements keyword search only, so the control is hidden. -->
            <UButton
              v-if="!isHttpMode"
              size="xs"
              :color="mode === 'semantic' ? 'primary' : 'neutral'"
              :variant="mode === 'semantic' ? 'soft' : 'ghost'"
              icon="i-lucide-brain"
              :label="t('core.search.modeSemantic')"
              @click="setMode('semantic')"
            />
          </div>
          <p class="text-xs text-muted">
            {{ mode === 'semantic' && !isHttpMode
              ? t('core.search.hintSemantic')
              : t('core.search.hintKeyword') }}
          </p>
        </div>
      </template>
    </UDashboardSearch>

    <UDashboardPanel
      id="main"
      class="min-w-0"
      :ui="{
        root: 'relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden',
        body: 'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-0 sm:p-0 gap-0',
      }"
    >
      <template
        v-if="!hidePosAppHeader"
        #header
      >
        <LayoutAppHeader />
      </template>
      <template #body>
        <div class="dashboard-page-slot flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <NuxtPage :page-key="page => page.fullPath" />
        </div>
      </template>
    </UDashboardPanel>
  </UDashboardGroup>
</template>
