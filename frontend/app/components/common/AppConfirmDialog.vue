<script setup lang="ts">
/**
 * Confirm dialog preset on top of the shared AppDialog shell.
 * Driven by useConfirm() via AppConfirmHost.
 */
const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(defineProps<{
  title?: string
  titleKey?: string
  description?: string
  descriptionKey?: string
  confirmLabel?: string
  confirmLabelKey?: string
  cancelLabel?: string
  cancelLabelKey?: string
  confirmColor?: 'error' | 'primary' | 'neutral' | 'warning'
  loading?: boolean
  ui?: Record<string, unknown>
}>(), {
  confirmColor: 'error',
  loading: false,
})

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const { t, te } = useI18n()

const resolvedTitle = computed(() => {
  if (props.title) return props.title
  if (props.titleKey && te(props.titleKey)) return t(props.titleKey)
  return t('core.common.confirmTitle')
})

const resolvedDescription = computed(() => {
  if (props.description) return props.description
  if (props.descriptionKey && te(props.descriptionKey)) return t(props.descriptionKey)
  return ''
})

const resolvedConfirm = computed(() => {
  if (props.confirmLabel) return props.confirmLabel
  if (props.confirmLabelKey && te(props.confirmLabelKey)) return t(props.confirmLabelKey)
  return t('core.common.confirm')
})

const resolvedCancel = computed(() => {
  if (props.cancelLabel) return props.cancelLabel
  if (props.cancelLabelKey && te(props.cancelLabelKey)) return t(props.cancelLabelKey)
  return t('core.common.cancel')
})

function onCancel() {
  open.value = false
  emit('cancel')
}

function onConfirm() {
  emit('confirm')
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="resolvedTitle"
    :description="resolvedDescription"
    icon="i-lucide-message-circle-question"
    size="sm"
    :dismissible="false"
    :loading="loading"
    :ui="props.ui"
  >
    <slot />

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :disabled="loading"
          :label="resolvedCancel"
          @click="onCancel"
        />
        <UButton
          :color="confirmColor"
          :loading="loading"
          :label="resolvedConfirm"
          @click="onConfirm"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>