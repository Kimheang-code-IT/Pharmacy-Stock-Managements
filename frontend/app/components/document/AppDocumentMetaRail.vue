<script setup lang="ts">
import type { TimelineItem } from '@nuxt/ui'
import type { PersonSummary } from '~/types/stock-pos/common'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

const props = defineProps<{
  title?: string
  subtitle?: string
  /** Module icon shown in the record tile instead of the first letter. */
  icon?: string
  owner?: PersonSummary
  createdAt?: string
  updatedAt?: string
}>()

const { t } = useI18n()
const { relativeTime } = useAppLocalization()

const relativeLabels = computed(() => ({
  justNow: t('core.meta.justNow'),
  minuteAgo: t('core.meta.minuteAgo'),
  minutesAgo: (n: number) => t('core.meta.minutesAgo', { n }),
  hourAgo: t('core.meta.hourAgo'),
  hoursAgo: (n: number) => t('core.meta.hoursAgo', { n }),
  dayAgo: t('core.meta.dayAgo'),
  daysAgo: (n: number) => t('core.meta.daysAgo', { n }),
}))

function formatRelativeStamp(value?: string) {
  if (!value) return ''
  return relativeTime(value, relativeLabels.value, { fallback: value })
}

const initial = computed(() => {
  const text = (props.title || '').trim()
  return text ? text.charAt(0).toUpperCase() : '—'
})

const stampItems = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = []
  if (props.updatedAt) {
    items.push({
      value: 'updated',
      date: formatRelativeStamp(props.updatedAt),
      title: `${t('core.meta.lastEditedBy')} ${t('core.meta.you')}`,
      icon: 'i-lucide-pencil',
    })
  }
  if (props.createdAt) {
    items.push({
      value: 'created',
      date: formatRelativeStamp(props.createdAt),
      title: `${t('core.meta.createdBy')} ${props.owner?.name || t('core.meta.you')}`,
      icon: 'i-lucide-plus',
    })
  }
  return items
})
</script>

<template>
  <aside class="flex w-full shrink-0 flex-col border-default bg-default lg:w-64 xl:w-72 lg:border-s">
    <section class="flex items-start gap-3 border-b border-default p-4">
      <div class="grid size-14 shrink-0 place-items-center rounded-sm bg-elevated">
        <UIcon v-if="icon" :name="icon" class="size-7 text-toned" />
        <span v-else class="text-xl font-semibold text-toned">{{ initial }}</span>
      </div>
      <div class="min-w-0 flex-1 pt-0.5">
        <p class="truncate text-sm font-semibold text-highlighted">{{ title || '—' }}</p>
        <p v-if="subtitle" class="mt-0.5 truncate text-xs text-muted">{{ subtitle }}</p>
      </div>
    </section>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <UTimeline
        v-if="stampItems.length"
        :items="stampItems"
        color="neutral"
        size="xs"
        class="w-full"
        :ui="{
          item: 'pb-1 last:pb-0',
          wrapper: 'ms-1 pb-4',
          date: 'text-xs text-muted',
          title: 'text-xs text-toned',
          description: 'text-xs text-muted',
        }"
      />
    </div>
  </aside>
</template>
