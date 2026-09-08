<script setup lang="ts">
import type { DocumentTabSchema } from '~/types/stock-pos/common'

const props = defineProps<{
  tabs: DocumentTabSchema[]
  activeTab: string
}>()

const emit = defineEmits<{
  'update:activeTab': [string]
}>()

const { t, te } = useI18n()

const tabItems = computed(() =>
  props.tabs.map(tab => ({
    label: tab.labelKey && te(tab.labelKey) ? t(tab.labelKey) : (tab.label || tab.id),
    value: tab.id,
  })),
)

const scroller = ref<HTMLElement | null>(null)

/** Wheel over the strip pans the tabs sideways instead of scrolling the page. */
function onWheel(event: WheelEvent) {
  const el = scroller.value
  if (!el || el.scrollWidth <= el.clientWidth) return
  if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return
  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY
  const max = el.scrollWidth - el.clientWidth
  el.scrollLeft = Math.min(max, Math.max(0, el.scrollLeft + delta))
  event.preventDefault()
}
</script>

<template>
  <div
    v-if="tabs.length"
    class="w-full shrink-0 border-b border-default bg-default"
  >
    <div
      ref="scroller"
      class="w-full touch-pan-x overflow-x-auto overflow-y-hidden overscroll-x-contain scrollbar-none"
      @wheel="onWheel"
    >
      <UTabs
        :model-value="activeTab"
        :items="tabItems"
        :content="false"
        color="neutral"
        variant="link"
        size="md"
        class="min-w-max"
        :ui="{
          root: 'min-w-max gap-0',
          list: 'relative min-w-max w-max gap-0 rounded-none bg-transparent border-b-0 px-4 sm:px-6 lg:px-10',
          trigger: [
            'grow-0 shrink-0 justify-center whitespace-nowrap rounded-none px-4 pt-2.5 pb-2.5 -mb-px',
            'border-b-2 border-transparent font-normal text-muted',
            'data-[state=active]:border-highlighted data-[state=active]:font-medium data-[state=active]:text-highlighted',
          ].join(' '),
          indicator: 'hidden',
        }"
        @update:model-value="(value: string | number) => emit('update:activeTab', String(value))"
      />
    </div>
  </div>
</template>
