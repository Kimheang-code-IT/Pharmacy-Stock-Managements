<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import type { PrintPaperSize } from '~/utils/print/html'

/**
 * POS inline payment keypad: an on-screen numeric keypad (tablet/iPad friendly)
 * that replaces the checkout summary block to enter the amount paid for this
 * invoice. Shows the total due plus the change (overpay) or outstanding balance
 * (underpay) live as digits are tapped.
 */
const props = withDefaults(defineProps<{
  total: number
  /** Delivery fee included in `total` (0 when no delivery). */
  deliveryPrice?: number
  currency?: 'USD' | 'KHR'
  paymentMethod?: string
  busy?: boolean
  disabled?: boolean
}>(), {
  deliveryPrice: 0,
  currency: 'USD',
  paymentMethod: 'Cash',
  busy: false,
  disabled: false,
})

const emit = defineEmits<{
  confirm: [amount: number]
  cancel: []
}>()

/** Invoice paper size chosen on the keypad (A4 / A5). */
const paperSize = defineModel<PrintPaperSize>('paperSize', { default: 'A4' })

const { t } = useI18n()

const entry = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

const isKhr = computed(() => props.currency === 'KHR')
const isCredit = computed(() => props.paymentMethod === 'Credit')
const symbol = computed(() => (isKhr.value ? '៛' : '$'))
/** Auto-sized so long amounts always fit (min 3ch). */
const inputWidth = computed(() => `${Math.max(3, entry.value.length + 1)}ch`)
const money = (value: unknown) => formatMoney(Number(value || 0), props.currency)

const amount = computed(() => {
  const value = Number(entry.value)
  return Number.isFinite(value) ? Math.max(0, value) : 0
})
const change = computed(() => Math.max(0, amount.value - Number(props.total || 0)))
const outstanding = computed(() => Math.max(0, Number(props.total || 0) - amount.value))
/** Sale amount before the delivery fee (only shown when delivery is added). */
const subtotal = computed(() => Math.max(0, Number(props.total || 0) - Number(props.deliveryPrice || 0)))

function prefill() {
  entry.value = isCredit.value ? '0' : String(Number(props.total || 0))
}

function focusInput() {
  void nextTick(() => inputEl.value?.focus())
}

onMounted(() => {
  prefill()
  focusInput()
})

/** Keep the amount to digits + at most one dot (two decimals for USD). */
function sanitize(value: string): string {
  let next = String(value ?? '').replace(/[^\d.]/g, '')
  const firstDot = next.indexOf('.')
  if (firstDot !== -1) {
    next = `${next.slice(0, firstDot + 1)}${next.slice(firstDot + 1).replace(/\./g, '')}`
  }
  if (isKhr.value) next = next.replace(/\./g, '')
  const [intPart, decPart] = next.split('.')
  if (decPart != null) next = `${intPart}.${decPart.slice(0, 2)}`
  return next
}

function onInput(event: Event) {
  const el = event.target as HTMLInputElement
  const clean = sanitize(el.value)
  entry.value = clean
  if (el.value !== clean) el.value = clean
}

function press(key: string) {
  if (props.disabled) return
  if (key === 'C') {
    entry.value = ''
    focusInput()
    return
  }
  if (key === 'back') {
    entry.value = entry.value.slice(0, -1)
    focusInput()
    return
  }
  if (key === 'exact') {
    prefill()
    focusInput()
    return
  }
  if (key === '.') {
    if (isKhr.value || entry.value.includes('.')) return
    entry.value = `${entry.value || '0'}.`
    focusInput()
    return
  }
  if (key === '00') {
    if (entry.value) entry.value += '00'
    focusInput()
    return
  }
  // Decimal guard (USD keeps at most two decimals).
  const [, decimals = ''] = entry.value.split('.')
  if (entry.value.includes('.') && decimals.length >= 2) return
  entry.value = entry.value === '0' ? key : entry.value + key
  focusInput()
}

const keys = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['.', '0', 'back'],
] as const

function confirm() {
  if (props.disabled || props.busy) return
  emit('confirm', amount.value)
}
</script>

<template>
  <div class="flex flex-1 flex-col gap-3">
    <!-- Paper size toggle (replaces the post-sale print dialog). -->
    <div class="grid grid-cols-2 gap-2">
      <UButton
        block
        size="lg"
        :color="paperSize === 'A4' ? 'primary' : 'neutral'"
        :variant="paperSize === 'A4' ? 'solid' : 'soft'"
        :label="t('app.pos.paperA4')"
        @click="paperSize = 'A4'"
      />
      <UButton
        block
        size="lg"
        :color="paperSize === 'A5' ? 'primary' : 'neutral'"
        :variant="paperSize === 'A5' ? 'solid' : 'soft'"
        :label="t('app.pos.paperA5')"
        @click="paperSize = 'A5'"
      />
    </div>

    <div
      v-if="Number(deliveryPrice) > 0"
      class="grid gap-1 rounded-sm bg-elevated/60 px-3 py-2 text-sm"
    >
      <div class="flex items-center justify-between">
        <span class="text-muted">{{ t('app.pos.subtotal') }}</span>
        <span class="tabular-nums">{{ money(subtotal) }}</span>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-muted">{{ t('app.pos.deliveryPrice') }}</span>
        <span class="tabular-nums">{{ money(deliveryPrice) }}</span>
      </div>
    </div>
    <div class="flex items-center justify-between rounded-sm bg-elevated/60 px-3 py-2 text-base">
      <span class="text-muted">{{ t('app.pos.total') }}</span>
      <span class="font-semibold tabular-nums">{{ money(total) }}</span>
    </div>

    <div class="flex items-center gap-2 border-b border-default pb-2">
      <span class="shrink-0 text-sm text-muted">{{ t('app.pos.paidAmount') }}</span>
      <div class="flex flex-1 items-center justify-center gap-1">
        <span class="shrink-0 text-2xl font-bold text-muted">{{ symbol }}</span>
        <input
          ref="inputEl"
          :value="entry"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="min-w-0 max-w-full bg-transparent text-center text-3xl font-bold tabular-nums text-highlighted outline-none placeholder:text-muted"
          :style="{ width: inputWidth }"
          placeholder="0"
          :disabled="disabled"
          @input="onInput"
          @keydown.enter.prevent="confirm"
        >
      </div>
    </div>

    <div
      v-if="change > 0"
      class="flex justify-between text-base font-semibold text-success"
    >
      <span>{{ t('app.pos.changeDue') }}</span>
      <span class="tabular-nums">{{ money(change) }}</span>
    </div>
    <div
      v-else-if="outstanding > 0"
      class="flex justify-between text-base font-semibold text-warning"
    >
      <span>{{ t('app.pos.outstandingAmount') }}</span>
      <span class="tabular-nums">{{ money(outstanding) }}</span>
    </div>

    <!-- Keypad + Back/Submit anchored to the bottom of the block. -->
    <div class="mt-auto grid gap-2">
      <div class="grid grid-cols-3 gap-2">
        <template
          v-for="row in keys"
          :key="row.join('-')"
        >
          <UButton
            v-for="key in row"
            :key="key"
            block
            size="xl"
            color="neutral"
            variant="soft"
            class="min-h-14 text-xl"
            :icon="key === 'back' ? 'i-lucide-delete' : undefined"
            :label="key === 'back' ? undefined : key"
            :disabled="disabled"
            @click="press(key)"
          />
        </template>
      </div>

      <div class="flex gap-2">
        <UButton
          class="h-14 flex-1 justify-center"
          color="neutral"
          variant="soft"
          size="lg"
          icon="i-lucide-arrow-left"
          :label="t('app.pos.backToCart')"
          :disabled="busy"
          @click="emit('cancel')"
        />
        <UButton
          class="h-14 flex-1 justify-center"
          color="primary"
          size="lg"
          :label="t('app.pos.submit')"
          :loading="busy"
          :disabled="disabled || entry === ''"
          @click="confirm"
        />
      </div>
    </div>
  </div>
</template>
