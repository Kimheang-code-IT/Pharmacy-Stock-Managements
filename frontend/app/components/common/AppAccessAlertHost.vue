<script setup lang="ts">
/**
 * Access/session alert host — thin consumer of the shared AppDialog.
 * Behavior lives in useAccessAlert(); this host owns no modal markup.
 */
import { useAccessAlert } from '~/composables/common/useAccessAlert'

const { state, close } = useAccessAlert()
const { t } = useI18n()

const isSessionExpired = computed(() => state.value.kind === 'session-expired')
const title = computed(() => isSessionExpired.value
  ? t('core.states.sessionExpiredTitle')
  : t('core.states.accessDeniedTitle'))
const description = computed(() => state.value.description || (isSessionExpired.value
  ? t('core.states.sessionExpiredDescription')
  : t('core.states.accessDeniedDescription')))
const actionLabel = computed(() => isSessionExpired.value
  ? t('core.states.signInAgain')
  : t('core.common.ok'))

const open = computed({
  get: () => state.value.open,
  set: (value: boolean) => {
    if (!value) close()
  },
})

function acknowledge() {
  close()
  if (isSessionExpired.value) void navigateTo('/auth/login')
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    :description="description"
    :icon="isSessionExpired ? 'i-lucide-clock-alert' : 'i-lucide-shield-alert'"
    :color="isSessionExpired ? 'warning' : 'error'"
    size="sm"
    :dismissible="false"
    :ui="{ overlay: 'z-[250]', content: 'z-[250]' }"
  >
    <div
      v-if="!isSessionExpired && (state.requestedPath || state.permission)"
      class="space-y-2 rounded-sm bg-elevated/60 p-3 text-xs"
    >
      <div v-if="state.requestedPath" class="grid gap-1 sm:grid-cols-[9rem_1fr]">
        <span class="font-medium text-muted">{{ $t('core.states.requestedPage') }}</span>
        <span class="break-all text-highlighted">{{ state.requestedPath }}</span>
      </div>
      <div v-if="state.permission" class="grid gap-1 sm:grid-cols-[9rem_1fr]">
        <span class="font-medium text-muted">{{ $t('core.states.requiredPermission') }}</span>
        <span class="break-all font-mono text-highlighted">{{ state.permission }}</span>
      </div>
    </div>

    <template #footer>
      <div class="flex w-full justify-end">
        <UButton :color="isSessionExpired ? 'warning' : 'error'" :label="actionLabel" @click="acknowledge" />
      </div>
    </template>
  </CommonAppDialog>
</template>