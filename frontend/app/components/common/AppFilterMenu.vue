<script setup lang="ts">
/**
 * Toolbar filter container: below desktop widths every filter (selects + date
 * range) collapses into one icon button that opens a popover menu.
 */
import { useMediaQuery } from '@vueuse/core'

const props = withDefaults(defineProps<{
  /** Lights the filter button while any filter inside the menu is set. */
  active?: boolean
  label?: string
}>(), {
  active: false,
  label: '',
})

const { t } = useI18n()
/** Collapse below xl — toolbars with 3-4 selects plus a date range only fit wider. */
const isCompact = useMediaQuery('(max-width: 1279px)')
const menuLabel = computed(() => props.label || t('components.filterMenu'))
</script>

<template>
  <div class="flex min-w-0 items-center" :class="isCompact ? 'shrink-0' : 'justify-end gap-2'">
    <UPopover v-if="isCompact" :content="{ align: 'end', side: 'bottom' }">
      <UButton
        :color="active ? 'primary' : 'neutral'"
        :variant="active ? 'soft' : 'outline'"
        icon="i-lucide-sliders-horizontal"
        size="sm"
        square
        :aria-label="menuLabel"
        :title="menuLabel"
      />
      <template #content>
        <div class="flex w-72 max-w-[calc(100vw-2rem)] flex-col items-stretch gap-3 p-3">
          <slot :compact="true" />
        </div>
      </template>
    </UPopover>

    <template v-else>
      <slot :compact="false" />
    </template>
  </div>
</template>
