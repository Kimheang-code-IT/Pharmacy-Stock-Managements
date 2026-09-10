<script setup lang="ts">
/**
 * Delivery info for the POS checkout Delivery checkbox (spec §5.11/§2.1.9):
 * opening phone, delivery location and the delivery price for THIS invoice.
 * Phone/location default from the customer snapshot and flow into the
 * post-sale Create Delivery Note (stored on delivery_notes.delivery_phone /
 * delivery_location — shown on the Delivery Notes table). No driver/vehicle
 * form.
 */
const props = defineProps<{
  /** Customer snapshot phone (prefill). */
  customerPhone: string
  /** Customer snapshot address/location (prefill). */
  customerLocation: string
  /** Delivery price typed for this invoice (document currency). */
  deliveryPrice: number
  disabled?: boolean
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  'update:deliveryPhone': [value: string]
  'update:deliveryLocation': [value: string]
  'update:deliveryPrice': [value: number]
  confirm: []
}>()

const { t } = useI18n()
const fieldUi = { base: 'text-base' }

const phone = ref('')
const location = ref('')
const priceInput = ref<number | undefined>(undefined)

/** Prefill from the customer snapshot each time the dialog opens. */
watch(open, (value) => {
  if (!value) return
  phone.value = props.customerPhone
  location.value = props.customerLocation
  priceInput.value = props.deliveryPrice
})

function emitPrice(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:deliveryPrice', Number.isFinite(amount) ? Math.max(0, amount) : 0)
}

function confirm() {
  emit('update:deliveryPhone', phone.value.trim())
  emit('update:deliveryLocation', location.value.trim())
  emitPrice(priceInput.value)
  open.value = false
  emit('confirm')
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.pos.deliveryInfoTitle')"
    icon="i-lucide-truck"
    size="sm"
  >
    <div class="grid gap-3">
      <UFormField
        :label="t('app.pos.deliveryPhone')"
        size="md"
      >
        <UInput
          :model-value="phone"
          class="w-full"
          size="lg"
          :ui="fieldUi"
          placeholder="012 xxx xxx"
          :disabled="disabled"
          @update:model-value="phone = String($event ?? '')"
        />
      </UFormField>
      <UFormField
        :label="t('app.pos.deliveryLocation')"
        size="md"
      >
        <UInput
          :model-value="location"
          class="w-full"
          size="lg"
          :ui="fieldUi"
          :placeholder="t('app.pos.locationPlaceholder')"
          :disabled="disabled"
          @update:model-value="location = String($event ?? '')"
        />
      </UFormField>
      <UFormField
        :label="t('app.pos.deliveryPrice')"
        size="md"
      >
        <UInputNumber
          :model-value="priceInput"
          :min="0"
          :step="0.01"
          :increment="false"
          :decrement="false"
          class="w-full"
          size="lg"
          :ui="{ base: 'text-base tabular-nums' }"
          :disabled="disabled"
          @update:model-value="emitPrice($event)"
        />
      </UFormField>
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          :disabled="disabled"
          @click="open = false"
        />
        <UButton
          color="primary"
          :label="t('actions.confirm')"
          :disabled="disabled"
          @click="confirm"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>