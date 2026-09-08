<script setup lang="ts">
import type { ConnectionStatus } from '~/types/stock-pos/settings'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

const props = defineProps<{
  status: ConnectionStatus
  title?: string
  titleKey?: string
  message?: string
  lastTestedAt?: string
  details?: Array<{ label: string, value: string }>
}>()

const { t, te } = useI18n()
const { formatDateTime } = useAppLocalization()

const titleText = computed(() => {
  if (props.title) return props.title
  if (props.titleKey && te(props.titleKey)) return t(props.titleKey)
  return t('core.connection.title')
})

const statusMeta = computed(() => {
  const map: Record<ConnectionStatus, { color: 'neutral' | 'primary' | 'success' | 'error' | 'warning', icon: string, labelKey: string }> = {
    not_tested: { color: 'neutral', icon: 'i-lucide-circle-dashed', labelKey: 'core.connection.notTested' },
    testing: { color: 'primary', icon: 'i-lucide-loader-circle', labelKey: 'core.connection.testing' },
    connected: { color: 'success', icon: 'i-lucide-circle-check', labelKey: 'core.connection.connected' },
    failed: { color: 'error', icon: 'i-lucide-circle-x', labelKey: 'core.connection.failed' },
    disabled: { color: 'warning', icon: 'i-lucide-ban', labelKey: 'core.connection.disabled' },
  }
  return map[props.status]
})
</script>

<template>
  <UCard :ui="{ body: 'space-y-3' }">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-medium text-highlighted">
          {{ titleText }}
        </p>
      </div>
      <UBadge :color="statusMeta.color" variant="subtle" class="shrink-0">
        <UIcon :name="statusMeta.icon" class="size-3.5" :class="status === 'testing' ? 'animate-spin' : ''" />
        <span class="ms-1">{{ t(statusMeta.labelKey) }}</span>
      </UBadge>
    </div>

    <p v-if="message" class="text-sm text-muted">
      {{ message }}
    </p>

    <p v-if="lastTestedAt" class="text-xs text-muted">
      {{ t('core.connection.lastTested') }}:
      {{ formatDateTime(lastTestedAt) }}
    </p>

    <dl v-if="details?.length" class="grid gap-2 text-sm sm:grid-cols-2">
      <div v-for="item in details" :key="item.label">
        <dt class="text-xs text-muted">
          {{ item.label }}
        </dt>
        <dd class="font-medium text-highlighted">
          {{ item.value }}
        </dd>
      </div>
    </dl>

    <slot />
  </UCard>
</template>
