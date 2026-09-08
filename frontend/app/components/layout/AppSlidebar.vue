<script setup lang="ts">
import { useMenu } from '~/composables/layout/useMenu'

const { t } = useI18n()
const { open, collapsed, links, setCollapsed } = useMenu()

const collapsedModel = computed({
  get: () => collapsed.value,
  set: (value: boolean) => setCollapsed(value),
})

/**
 * Below `lg`, Nuxt UI hides the desktop rail and opens a slideover.
 * Make that panel a full-height column so the user menu footer stays
 * pinned on iPad/tablet (long nav must not push it off-screen).
 */
const sidebarUi = computed(() => ({
  root: 'app-sidebar bg-muted/50 border-e border-default',
  // Slideover panel (< lg / iPad): flex column + full height keeps footer visible.
  content: 'lg:hidden flex h-full max-h-svh flex-col',
  header: collapsedModel.value
    ? 'h-auto flex-col items-center justify-center gap-2 px-0 pt-3 pb-2 shrink-0'
    : 'h-auto flex-col items-stretch gap-3 px-3 pt-3 pb-2 shrink-0',
  body: collapsedModel.value
    ? 'flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto px-0 py-1'
    : 'flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 py-1',
  footer: collapsedModel.value
    ? 'shrink-0 flex items-center justify-center border-t border-default px-0 py-3'
    : 'shrink-0 flex items-center gap-1.5 border-t border-default px-3 py-2',
}))
</script>

<template>
  <UDashboardSidebar
    id="default"
    v-model:open="open"
    v-model:collapsed="collapsedModel"
    collapsible
    resizable
    :min-size="12"
    :default-size="15"
    :max-size="20"
    :collapsed-size="4"
    :ui="sidebarUi"
  >
    <template #resize-handle="{ onMouseDown, onTouchStart, onDoubleClick }">
      <UDashboardResizeHandle
        class="after:absolute after:inset-y-0 after:right-0 after:w-px hover:after:bg-(--ui-border-accented) after:transition"
        @mousedown="onMouseDown"
        @touchstart="onTouchStart"
        @dblclick="onDoubleClick"
      />
    </template>

    <template #header="{ collapsed: isCollapsed }">
      <NuxtLink
        to="/"
        class="flex items-center"
        :class="isCollapsed ? 'justify-center' : 'gap-3 px-1'"
        :aria-label="t('core.brand.name')"
      >
        <span
          class="grid shrink-0 place-items-center overflow-hidden"
          :class="isCollapsed ? 'size-9' : 'size-12'"
        >
          <LayoutAppBrandLogo :img-class="isCollapsed ? 'size-9 object-contain' : 'size-12 object-contain'" />
        </span>
        <span v-if="!isCollapsed" class="min-w-0">
          <span class="app-sidebar-text block truncate text-lg font-bold tracking-tight">{{ t('core.brand.shortName') }}</span>
          <span class="app-sidebar-text block truncate text-[10px] uppercase tracking-[0.16em] opacity-60">{{ t('core.brand.tagline') }}</span>
        </span>
      </NuxtLink>

      <UDashboardSearchButton
        :collapsed="isCollapsed"
        tooltip
        class="bg-transparent app-sidebar-text"
        :class="isCollapsed ? 'mx-auto' : 'ring-default'"
        :ui="isCollapsed
          ? {
              base: 'justify-center rounded-sm size-9 p-0 app-sidebar-text',
              leadingIcon: 'app-sidebar-text',
            }
          : {
              base: 'app-sidebar-text',
              label: 'app-sidebar-text',
              leadingIcon: 'app-sidebar-text',
            }"
      />
    </template>

    <template #default="{ collapsed: isCollapsed }">
      <UNavigationMenu
        :collapsed="isCollapsed"
        :items="links[0]"
        orientation="vertical"
        type="multiple"
        :default-value="['finance', 'master', 'configuration', 'administration']"
        :unmount-on-hide="false"
        tooltip
        popover
        :ui="isCollapsed
          ? {
              root: 'w-full items-center',
              list: 'w-full flex flex-col items-center gap-0.5',
              item: 'w-full flex justify-center',
              link: 'justify-center size-9 p-0 rounded-sm',
              linkLeadingIcon: 'size-5 app-sidebar-text group-hover:opacity-80 group-data-[active]:text-primary',
            }
          : {
              root: 'w-full',
              link: 'rounded-sm app-sidebar-text hover:opacity-80 data-[active]:text-primary',
              linkLeadingIcon: 'size-5 app-sidebar-text group-data-[active]:text-primary',
              linkLabel: 'app-sidebar-text group-data-[active]:text-primary',
              childLink: 'app-sidebar-text data-[active]:text-primary',
              childLinkLabel: 'app-sidebar-text data-[active]:text-primary',
              childLinkIcon: 'size-5 app-sidebar-text group-data-[active]:text-primary',
              label: 'app-sidebar-text font-semibold',
            }"
      />
      <UNavigationMenu
        v-if="links[1]?.length"
        :collapsed="isCollapsed"
        :items="links[1]"
        orientation="vertical"
        tooltip
        :ui="isCollapsed
          ? {
              root: 'w-full items-center',
              list: 'w-full flex flex-col items-center gap-0.5',
              item: 'w-full flex justify-center',
              link: 'justify-center size-9 p-0 rounded-sm',
              linkLeadingIcon: 'size-5 app-sidebar-text',
            }
          : {
              link: 'app-sidebar-text',
              linkLeadingIcon: 'size-5 app-sidebar-text',
              linkLabel: 'app-sidebar-text',
            }"
      />
    </template>

    <template #footer="{ collapsed: isCollapsed }">
      <LayoutUserMenu :collapsed="isCollapsed" />
    </template>
  </UDashboardSidebar>
</template>
