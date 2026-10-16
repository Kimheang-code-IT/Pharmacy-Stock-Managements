<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import { roundMoney } from '~/utils/pos/cart'
import type { PrintPaperSize } from '~/utils/print/html'

/**
 * POS inline payment keypad: an on-screen numeric keypad (tablet/iPad friendly)
 * that replaces the checkout summary block to enter the amount paid for this
 * invoice. Shows the total due plus the change (overpay) or outstanding balance
 * (underpay) live as digits are tapped.
 *
 * The $/៛ buttons are the CURRENCY the customer pays in: pressing one converts
 * the whole invoice to that currency (the parent converts the cart, delivery,
 * discount and paid amounts at the rate), so a riel payment produces a KHR
 * invoice and a dollar payment a USD invoice — the invoice, report and reprint
 * always show the currency that was actually paid. A KHR switch without a known
 * rate asks for it through the shared exchange-rate dialog first.
 */
const props = withDefaults(defineProps<{
  total: number
  /** Delivery fee included in `total` (0 when no delivery). */
  deliveryPrice?: number
  /** Existing-debt payment collected together with this sale (0 when none). */
  existingDebt?: number
  /**
   * Edit mode: prefill the input with the amount ALREADY paid on the invoice
   * instead of the full total, so a correction save never records a phantom
   * payment. Undefined = a new sale (prefill the full amount due).
   */
  prefillAmount?: number
  currency?: 'USD' | 'KHR'
  /** KHR per 1 USD — the invoice's own rate (0 when a switch must ask for it). */
  exchangeRate?: number
  paymentMethod?: string
  busy?: boolean
  disabled?: boolean
}>(), {
  deliveryPrice: 0,
  existingDebt: 0,
  prefillAmount: undefined,
  currency: 'USD',
  exchangeRate: 0,
  paymentMethod: 'Cash',
  busy: false,
  disabled: false,
})

const emit = defineEmits<{
  confirm: [amount: number]
  /** Paid-currency pressed: convert the whole invoice to it at the rate. */
  switchCurrency: [payload: { currency: 'USD' | 'KHR', rate: number }]
  cancel: []
}>()

/** Invoice paper size chosen on the keypad (A4 / A5). */
const paperSize = defineModel<PrintPaperSize>('paperSize', { default: 'A4' })

const { t } = useI18n()

const entry = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

/** Group the integer part with thousands separators (`#,##0.####`, display only). */
function groupEntry(raw: string): string {
  if (!raw) return ''
  const [intPart = '', decPart] = raw.split('.')
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return raw.includes('.') ? `${grouped}.${decPart ?? ''}` : grouped
}

/** Raw digits kept separately from the grouped text shown in the input. */
const display = computed(() => groupEntry(entry.value))

/** KHR switch awaiting a rate from the shared dialog. */
const pendingCurrency = ref<'KHR' | null>(null)
const rateDialogOpen = ref(false)

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

const isCredit = computed(() => props.paymentMethod === 'Credit')
const isKhr = computed(() => props.currency === 'KHR')
const symbol = computed(() => (isKhr.value ? '៛' : '$'))
/** Auto-sized so long amounts always fit (min 3ch). */
const inputWidth = computed(() => `${Math.max(3, display.value.length + 1)}ch`)
const money = (value: unknown) => formatMoney(Number(value || 0), props.currency)

/** KHR per 1 USD for this invoice; 0 when a currency switch must ask for it. */
const rate = computed(() => Math.max(0, Number(props.exchangeRate || 0)))

const amount = computed(() => {
  const value = Number(entry.value)
  return Number.isFinite(value) ? Math.max(0, value) : 0
})
/** Existing-debt payment folded into the keypad total (never negative). */
const debtAmount = computed(() => roundMoney(Math.max(0, Number(props.existingDebt || 0))))
/** The single amount to collect: this sale plus any existing-debt payment. */
const combinedTotal = computed(() => roundMoney(Math.max(0, Number(props.total || 0)) + debtAmount.value))
/** Cash handed back. */
const change = computed(() => Math.max(0, amount.value - combinedTotal.value))
/** Shortfall recorded as debt. */
const outstanding = computed(() => Math.max(0, combinedTotal.value - amount.value))
/** Sale amount before the delivery fee (only shown when delivery is added). */
const subtotal = computed(() => Math.max(0, Number(props.total || 0) - Number(props.deliveryPrice || 0)))

function roundEntry(value: number) {
  if (isKhr.value) return Math.round(value)
  return Math.round((Number(value) || 0) * 10000) / 10000
}

function prefill() {
  if (isCredit.value) {
    entry.value = '0'
    return
  }
  // Edit mode: default to what is already paid on this invoice (keeps the
  // paid/debt state unless the cashier explicitly enters more).
  const due = props.prefillAmount != null
    ? Math.max(0, Number(props.prefillAmount) || 0)
    : combinedTotal.value
  entry.value = String(roundEntry(due))
}

function focusInput() {
  void nextTick(() => inputEl.value?.focus())
}

onMounted(() => {
  prefill()
  focusInput()
})

/** The invoice currency just converted: show the (converted) amount to collect. */
watch(() => props.currency, () => {
  pendingCurrency.value = null
  prefill()
  focusInput()
})

/** Keep the amount to digits + at most one dot (four decimals for USD). */
function sanitize(value: string): string {
  let next = String(value ?? '').replace(/[^\d.]/g, '')
  const firstDot = next.indexOf('.')
  if (firstDot !== -1) {
    next = `${next.slice(0, firstDot + 1)}${next.slice(firstDot + 1).replace(/\./g, '')}`
  }
  if (isKhr.value) next = next.replace(/\./g, '')
  const [intPart, decPart] = next.split('.')
  if (decPart != null) next = `${intPart}.${decPart.slice(0, 4)}`
  return next
}

function onInput(event: Event) {
  const el = event.target as HTMLInputElement
  const clean = sanitize(el.value)
  entry.value = clean
  const shown = groupEntry(clean)
  if (el.value !== shown) el.value = shown
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
  // Decimal guard (USD keeps at most four decimals).
  const [, decimals = ''] = entry.value.split('.')
  if (entry.value.includes('.') && decimals.length >= 4) return
  entry.value = entry.value === '0' ? key : entry.value + key
  focusInput()
}

/** $/៛ pressed: the customer pays in this currency — switch the WHOLE invoice
 *  to it (asking for the USD→KHR rate first when it is not known yet). */
function selectCurrency(value: 'USD' | 'KHR') {
  if (props.disabled || value === props.currency) return
  if (value === 'KHR' && rate.value <= 0) {
    pendingCurrency.value = 'KHR'
    rateDialogOpen.value = true
    return
  }
  emit('switchCurrency', { currency: value, rate: rate.value })
}

/** Shared rate dialog confirmed: convert the invoice to KHR at this rate. */
function onRateConfirm(value: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return
  const target = pendingCurrency.value
  pendingCurrency.value = null
  if (target) emit('switchCurrency', { currency: target, rate: parsed })
}

function confirm() {
  if (props.disabled || props.busy) return
  emit('confirm', roundMoney(amount.value))
}

const keys = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['.', '0', 'back'],
] as const
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
    <div
      v-if="debtAmount > 0"
      class="flex items-center justify-between rounded-sm bg-elevated/60 px-3 py-2 text-sm"
    >
      <span class="text-muted">{{ t('app.pos.depositTotal') }}</span>
      <span class="tabular-nums">{{ money(debtAmount) }}</span>
    </div>
    <div class="flex items-center justify-between rounded-sm bg-elevated/60 px-3 py-2 text-base">
      <span class="text-muted">{{ t('app.pos.total') }}</span>
      <span class="font-semibold tabular-nums">{{ money(combinedTotal) }}</span>
    </div>

    <div class="grid gap-2 border-b border-default pb-2">
      <div class="flex items-center justify-between">
        <span class="text-sm text-muted">{{ t('app.pos.paidAmount') }}</span>
        <div class="inline-flex overflow-hidden rounded-sm border border-default">
          <UButton
            v-for="option in currencyOptions"
            :key="option.value"
            size="xs"
            :color="currency === option.value ? 'primary' : 'neutral'"
            :variant="currency === option.value ? 'solid' : 'ghost'"
            :label="option.symbol"
            :title="t(option.labelKey)"
            :aria-label="t(option.labelKey)"
            :aria-pressed="currency === option.value"
            :disabled="disabled"
            @click="selectCurrency(option.value)"
          />
        </div>
      </div>
      <div class="flex items-center justify-center gap-1">
        <span class="shrink-0 text-2xl font-bold text-muted">{{ symbol }}</span>
        <input
          ref="inputEl"
          :value="display"
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

    <!-- Shared rate dialog: opened only when a KHR switch needs the USD rate. -->
    <CommonAppExchangeRateDialog
      v-model:open="rateDialogOpen"
      @confirm="onRateConfirm"
    />
  </div>
</template>
