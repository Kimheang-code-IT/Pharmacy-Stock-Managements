<script setup lang="ts">
/**
 * Shared exchange-rate dialog (1 USD = ? KHR). Opened by the shared
 * currency-toggle logic whenever a document switches to KHR; the rate
 * applies to every KHR amount on that document. Confirming emits the
 * validated rate; closing/cancelling lets the caller keep the previous
 * currency.
 */
const props = withDefaults(defineProps<{
  open?: boolean
  /** Pre-fill when a valid rate is already known (e.g. re-opening). */
  initialRate?: number
}>(), {
  open: false,
  initialRate: undefined,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [rate: number]
}>()

const { t } = useI18n()

const rateInput = ref<number | undefined>()
const touched = ref(false)

watch(() => props.open, (open) => {
  if (!open) return
  rateInput.value = props.initialRate != null && props.initialRate > 0
    ? props.initialRate
    : undefined
  touched.value = false
})

const rateInvalid = computed(() => touched.value && !(Number(rateInput.value || 0) > 0))

function onInput(value: number | undefined) {
  touched.value = true
  rateInput.value = value
}

function submit() {
  touched.value = true
  const rate = Number(rateInput.value || 0)
  if (!(rate > 0)) return
  emit('confirm', rate)
  emit('update:open', false)
}

function close() {
  emit('update:open', false)
}
</script>

<template>
  <CommonAppDialog
    :open="open"
    :title="t('app.pos.exchangeRate')"
    icon="i-lucide-arrow-right-left"
    size="sm"
    @update:open="value => value ? undefined : close()"
  >
    <div class="space-y-3">
      <p class="text-sm text-muted">
        {{ t('app.pos.exchangeRateDialogHint') }}
      </p>
      <UFormField
        :label="t('app.pos.exchangeRate')"
        :error="rateInvalid ? t('app.pos.exchangeRateInvalid') : undefined"
      >
        <UInputNumber
          :model-value="rateInput"
          :min="1"
          :step="1"
          :increment="false"
          :decrement="false"
          class="w-full"
          size="lg"
          :ui="{ base: 'text-base tabular-nums' }"
          :placeholder="t('app.pos.exchangeRatePlaceholder')"
          @update:model-value="onInput"
          @keydown.enter.prevent="submit"
        />
      </UFormField>
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="close"
        />
        <UButton
          icon="i-lucide-check"
          :disabled="!(Number(rateInput || 0) > 0)"
          :label="t('common.confirm')"
          @click="submit"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
