<script setup lang="ts">
/**
 * Single app-wide confirm dialog host.
 * Driven by useConfirm() — mount once in app.vue.
 */
import { useConfirm } from '~/composables/common/useConfirm'

const { confirmState, accept, dismiss } = useConfirm()
const { t, te } = useI18n()

const open = computed({
  get: () => confirmState.open,
  set: (value: boolean) => {
    if (!value && confirmState.open) dismiss()
  },
})

const title = computed(() => {
  if (confirmState.title) return confirmState.title
  if (confirmState.titleKey && te(confirmState.titleKey)) return t(confirmState.titleKey)
  return t('core.common.confirmTitle')
})

const description = computed(() => {
  if (confirmState.description) return confirmState.description
  if (confirmState.descriptionKey && te(confirmState.descriptionKey)) {
    return t(confirmState.descriptionKey, confirmState.descriptionParams || {})
  }
  return ''
})

const confirmLabel = computed(() => {
  if (confirmState.confirmLabel) return confirmState.confirmLabel
  if (confirmState.confirmLabelKey && te(confirmState.confirmLabelKey)) {
    return t(confirmState.confirmLabelKey)
  }
  return t('core.common.confirm')
})

const cancelLabel = computed(() => {
  if (confirmState.cancelLabel) return confirmState.cancelLabel
  if (confirmState.cancelLabelKey && te(confirmState.cancelLabelKey)) {
    return t(confirmState.cancelLabelKey)
  }
  return t('core.common.cancel')
})
</script>

<template>
  <CommonAppConfirmDialog
    v-model:open="open"
    :title="title"
    :description="description"
    :confirm-label="confirmLabel"
    :cancel-label="cancelLabel"
    :confirm-color="confirmState.confirmColor"
    :loading="confirmState.loading"
    :ui="{ overlay: 'z-[200]', content: 'z-[200]' }"
    @confirm="accept"
    @cancel="dismiss"
  />
</template>
