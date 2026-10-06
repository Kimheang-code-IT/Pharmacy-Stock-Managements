<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import { roundMoney } from '~/utils/pos/cart'
import type { PrintPaperSize } from '~/utils/print/html'

/**
 * POS inline payment keypad: an on-screen numeric keypad (tablet/iPad friendly)
 * that replaces the checkout summary block to enter the amount paid for this
 * invoice. Shows the total due plus the change (overpay) or outstanding balance
 * (underpay) live as digits are tapped. When the customer pays existing debt
 * together with this invoice, the keypad Total becomes sale + old debt so one
 * tender covers both.
 */
const props = withDefaults(defineProps<{
  total: number
  /** Delivery fee included in `total` (0 when no delivery). */
  deliveryPrice?: number
  /** Existing-debt payment collected together with this sale (0 when none). */
  existingDebt?: number
  currency?: 'USD' | 'KHR'
  /** KHR per 1 USD — reused to convert a cross-currency tender; 0 when unknown. */
  exchangeRate?: number
  paymentMethod?: string
  busy?: boolean
  disabled?: boolean
}>(), {
  deliveryPrice: 0,
  existingDebt: 0,
  currency: 'USD',
  exchangeRate: 0,
  paymentMethod: 'Cash',
  busy: false,
  disabled: false,
})

const emit = defineEmits<{
  confirm: [amount: number]
  /** Set when the shared rate dialog collects a rate needed for the tender. */
  'update:exchangeRate': [value: number]
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

/** Currency the cashier tenders in — independent of the invoice currency, so
 *  a USD invoice can be settled with riel (and vice versa) at the sale rate. */
const tenderCurrency = ref<'USD' | 'KHR'>(props.currency)
/** Cross-currency switch awaiting a rate from the shared dialog. */
const pendingTender = ref<'USD' | 'KHR' | null>(null)
const rateDialogOpen = ref(false)

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

const isCredit = computed(() => props.paymentMethod === 'Credit')
const isTenderKhr = computed(() => tenderCurrency.value === 'KHR')
const symbol = computed(() => (isTenderKhr.value ? '៛' : '$'))
/** Auto-sized so long amounts always fit (min 3ch). */
const inputWidth = computed(() => `${Math.max(3, display.value.length + 1)}ch`)
const money = (value: unknown) => formatMoney(Number(value || 0), props.currency)
const tenderMoney = (value: unknown) => formatMoney(Number(value || 0), tenderCurrency.value)

/** KHR per 1 USD, reused from the sale; 0 when not yet known. */
const rate = computed(() => Math.max(0, Number(props.exchangeRate || 0)))
/** Entered amount is in a different currency than the invoice. */
const crossCurrency = computed(() => tenderCurrency.value !== props.currency)

function toSaleCurrency(value: number): number {
  const amount = Number(value) || 0
  if (!crossCurrency.value || rate.value <= 0) return amount
  return props.currency === 'USD' ? amount / rate.value : amount * rate.value
}

function toTenderCurrency(value: number): number {
  const amount = Number(value) || 0
  if (!crossCurrency.value || rate.value <= 0) return amount
  return props.currency === 'USD' ? amount * rate.value : amount / rate.value
}

const amount = computed(() => {
  const value = Number(entry.value)
  return Number.isFinite(value) ? Math.max(0, value) : 0
})
/** Existing-debt payment folded into the keypad total (never negative). */
const debtAmount = computed(() => roundMoney(Math.max(0, Number(props.existingDebt || 0))))
/** The single amount to collect: this sale plus any existing-debt payment. */
const combinedTotal = computed(() => roundMoney(Math.max(0, Number(props.total || 0)) + debtAmount.value))
/** Combined total expressed in the tender currency (prefill / change). */
const combinedTotalTender = computed(() => toTenderCurrency(combinedTotal.value))
/** Cash handed back, in the tender currency. */
const change = computed(() => Math.max(0, amount.value - combinedTotalTender.value))
/** Shortfall recorded as debt — kept in the invoice currency. */
const outstanding = computed(() => Math.max(0, combinedTotal.value - toSaleCurrency(amount.value)))
/** Entered tender shown in the invoice currency while currencies differ. */
const equivalent = computed(() => toSaleCurrency(amount.value))
/** Sale amount before the delivery fee (only shown when delivery is added). */
const subtotal = computed(() => Math.max(0, Number(props.total || 0) - Number(props.deliveryPrice || 0)))

function roundTender(value: number) {
  if (tenderCurrency.value === 'KHR') return Math.round(value)
  return Math.round((Number(value) || 0) * 10000) / 10000
}

function prefill() {
  entry.value = isCredit.value ? '0' : String(roundTender(combinedTotalTender.value))
}

/** Invoice currency changed (new sale) — reset the tender currency with it. */
watch(() => props.currency, (value) => {
  tenderCurrency.value = value
  pendingTender.value = null
})

function focusInput() {
  void nextTick(() => inputEl.value?.focus())
}

onMounted(() => {
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
  if (isTenderKhr.value) next = next.replace(/\./g, '')
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
    if (isTenderKhr.value || entry.value.includes('.')) return
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

const keys = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['.', '0', 'back'],
] as const

/** Switch tender currency, converting the amount already entered. */
function applyTender(value: 'USD' | 'KHR', rateValue = rate.value) {
  if (value === tenderCurrency.value) return
  const current = amount.value
  let converted = current
  if (current > 0 && rateValue > 0) {
    if (tenderCurrency.value === 'USD' && value === 'KHR') converted = current * rateValue
    else if (tenderCurrency.value === 'KHR' && value === 'USD') converted = current / rateValue
  }
  tenderCurrency.value = value
  if (current > 0) entry.value = String(roundTender(converted))
  focusInput()
}

/** Toggle handler: cross-currency switches need a USD→KHR rate first. */
function selectTender(value: 'USD' | 'KHR') {
  if (props.disabled || value === tenderCurrency.value) return
  if (value !== props.currency && rate.value <= 0) {
    pendingTender.value = value
    rateDialogOpen.value = true
    return
  }
  applyTender(value)
}

/** Shared rate dialog confirmed: record the rate, then complete the switch. */
function onRateConfirm(value: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return
  emit('update:exchangeRate', parsed)
  const target = pendingTender.value
  pendingTender.value = null
  if (target) applyTender(target, parsed)
}

function confirm() {
  if (props.disabled || props.busy) return
  emit('confirm', roundMoney(toSaleCurrency(amount.value)))
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
            :color="tenderCurrency === option.value ? 'primary' : 'neutral'"
            :variant="tenderCurrency === option.value ? 'solid' : 'ghost'"
            :label="option.symbol"
            :title="t(option.labelKey)"
            :aria-label="t(option.labelKey)"
            :aria-pressed="tenderCurrency === option.value"
            :disabled="disabled"
            @click="selectTender(option.value)"
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
      <p
        v-if="crossCurrency && amount > 0"
        class="text-center text-sm tabular-nums text-muted"
      >
        ≈ {{ money(equivalent) }}
      </p>
    </div>

    <div
      v-if="change > 0"
      class="flex justify-between text-base font-semibold text-success"
    >
      <span>{{ t('app.pos.changeDue') }}</span>
      <span class="tabular-nums">{{ tenderMoney(change) }}</span>
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

    <!-- Shared rate dialog: opened only when a cross-currency tender needs it. -->
    <CommonAppExchangeRateDialog
      v-model:open="rateDialogOpen"
      :initial-rate="rate > 0 ? rate : undefined"
      @confirm="onRateConfirm"
    />
  </div>
</template>
