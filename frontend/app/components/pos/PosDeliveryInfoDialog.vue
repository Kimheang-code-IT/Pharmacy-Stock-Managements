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
  /** Document currency of the invoice (drives the price field symbol). */
  currency?: 'USD' | 'KHR'
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
/** Keypad text entry; kept in sync with the field (computer keyboard too). */
const priceText = ref('')

/** Prefill from the customer snapshot each time the dialog opens. */
watch(open, (value) => {
  if (!value) return
  phone.value = props.customerPhone
  location.value = props.customerLocation
  priceInput.value = props.deliveryPrice
  priceText.value = Number(props.deliveryPrice) > 0 ? String(props.deliveryPrice) : ''
})

/** Always-visible numeric keypad for the delivery price (tablet friendly). */
const keypadKeys = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['.', '0', 'back'],
] as const

function syncPrice(amount: number) {
  priceInput.value = amount
  emit('update:deliveryPrice', amount)
}

/** Direct field / computer-keyboard entry keeps the keypad text in sync. */
function onFieldInput(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  const safe = Number.isFinite(amount) ? Math.max(0, amount) : 0
  priceText.value = safe > 0 ? String(safe) : ''
  syncPrice(safe)
}

function pressKey(key: string) {
  if (key === 'back') {
    priceText.value = priceText.value.slice(0, -1)
  }
  else if (key === '.') {
    if (priceText.value.includes('.')) return
    priceText.value = `${priceText.value || '0'}.`
  }
  else {
    const [, decimals = ''] = priceText.value.split('.')
    if (priceText.value.includes('.') && decimals.length >= 2) return
    priceText.value = priceText.value === '0' ? key : priceText.value + key
  }
  const value = Number(priceText.value)
  syncPrice(Number.isFinite(value) ? Math.max(0, value) : 0)
}

function confirm() {
  emit('update:deliveryPhone', phone.value.trim())
  emit('update:deliveryLocation', location.value.trim())
  syncPrice(Number(priceInput.value || 0))
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
        <CommonAppMoneyField
          inline
          :model-value="priceInput"
          :currency="currency"
          :min="0"
          :step="0.01"
          class="w-full"
          size="lg"
          align="right"
          :disabled="disabled"
          @update:model-value="onFieldInput"
        />
      </UFormField>

      <!-- Always-visible numeric keypad for the delivery price. -->
      <div class="grid grid-cols-3 gap-2">
        <template
          v-for="row in keypadKeys"
          :key="row.join('-')"
        >
          <UButton
            v-for="key in row"
            :key="key"
            block
            size="xl"
            color="neutral"
            variant="soft"
            class="min-h-12 text-xl"
            :icon="key === 'back' ? 'i-lucide-delete' : undefined"
            :label="key === 'back' ? undefined : key"
            :disabled="disabled"
            @click="pressKey(key)"
          />
        </template>
      </div>
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