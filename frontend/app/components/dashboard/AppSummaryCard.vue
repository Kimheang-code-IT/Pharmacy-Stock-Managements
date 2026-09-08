<script setup lang="ts">
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

/**
 * Reusable dashboard / report summary metric card.
 * Matches compact title + value + overflow menu pattern.
 */
const props = withDefaults(
  defineProps<{
    title: string
    value: string | number | null | undefined
    /** Optional deep link when the card (or View action) is activated */
    to?: string
    trend?: number | null
    /** Format helpers — default shows the raw value (NaN/null → "—") */
    prefix?: string
    suffix?: string
    decimals?: number
    loading?: boolean
  }>(),
  {
    to: undefined,
    trend: null,
    prefix: '',
    suffix: '',
    decimals: undefined,
    loading: false,
  },
)

const emit = defineEmits<{
  refresh: []
  select: []
}>()

const { t } = useI18n()
const { formatNumber } = useAppLocalization()

const displayValue = computed(() => {
  const raw = props.value
  if (raw == null || raw === '') return '—'
  const num = typeof raw === 'number' ? raw : Number(raw)
  if (typeof raw === 'number' || (typeof raw === 'string' && raw.trim() !== '' && !Number.isNaN(num))) {
    if (Number.isNaN(num)) return '—'
    const formatted = props.decimals != null
      ? formatNumber(num, {
          minimumFractionDigits: props.decimals,
          maximumFractionDigits: props.decimals,
        })
      : formatNumber(num)
    return `${props.prefix}${formatted}${props.suffix}`
  }
  return `${props.prefix}${raw}${props.suffix}`
})

const menuItems = computed(() => {
  const items: Array<{ label: string, icon?: string, to?: string, onSelect?: () => void }> = []
  if (props.to) {
    items.push({
      label: t('core.actions.viewAll'),
      icon: 'i-lucide-arrow-up-right',
      to: props.to,
    })
  }
  items.push({
    label: t('core.actions.refresh'),
    icon: 'i-lucide-refresh-cw',
    onSelect: () => emit('refresh'),
  })
  return [items]
})

function onActivate() {
  emit('select')
  if (props.to) navigateTo(props.to)
}
</script>

<template>
  <div
    class="flex flex-col rounded-sm border border-default bg-default p-3"
    :class="to ? 'cursor-pointer hover:border-accented' : ''"
    :role="to ? 'link' : 'group'"
    :tabindex="to ? 0 : undefined"
    @click="to ? onActivate() : undefined"
    @keydown.enter.prevent="to ? onActivate() : undefined"
  >
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 text-sm font-medium text-highlighted">
        {{ title }}
      </p>
      <UDropdownMenu :items="menuItems" :content="{ align: 'end' }">
        <UButton
          icon="i-lucide-ellipsis"
          color="neutral"
          variant="ghost"
          size="xs"
          class="shrink-0 -mr-1 -mt-1"
          :aria-label="$t('core.actions.more')"
          @click.stop
        />
      </UDropdownMenu>
    </div>

    <div class="mt-3 flex items-end gap-2">
      <p v-if="loading" class="text-2xl font-semibold tabular-nums text-muted">
        …
      </p>
      <p v-else class="text-lg font-semibold tabular-nums tracking-tight text-highlighted">
        {{ displayValue }}
      </p>
      <span
        v-if="trend != null && !loading"
        class="mb-0.5 text-xs font-medium"
        :class="trend >= 0 ? 'text-success' : 'text-error'"
      >
        {{ trend >= 0 ? '+' : '' }}{{ trend }}%
      </span>
    </div>

    <slot />
  </div>
</template>
