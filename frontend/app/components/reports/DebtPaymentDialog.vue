<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { PAYMENT_METHODS } from '~/config/pos-options'
import { formatMoney } from '~/composables/module/useModule'
import { formatNumber } from '~/utils/format/format-service'
import { convertAmount, roundMoney } from '~/utils/pos/cart'
import { debtCurrency } from '~/utils/reports/debts'

export type DebtPaymentKind = 'customer' | 'supplier'

/**
 * Record a payment against one customer or supplier debt summary row.
 * Modal only — opened from Customer / Supplier Debt Report row actions.
 *
 * The payment currency option ($/៛) picks the currency the customer is
 * COLLECTING IN: the amount is typed in that currency, converted at the
 * exchange rate and settles the debt (which keeps its own invoice currency).
 * The receipt prints the collected amount next to the settled one.
 */
const props = defineProps<{
  kind: DebtPaymentKind
  debt: AppRecord | null
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  submit: [payload: {
    kind: DebtPaymentKind
    partyId: string
    /** Settled amount in the debt document's own currency. */
    amount: number
    paymentMethod: string
    /** Document currency of the settled side (row is per party + currency). */
    currency: string
    /** Currency the cashier actually collected (USD | KHR). */
    collectedCurrency: string
    /** Collected amount, in `collectedCurrency`. */
    collectedAmount: number
    /** KHR per 1 USD used when the collected currency differs, else null. */
    exchangeRate: number | null
  }]
}>()

const { t } = useI18n()
const preferences = usePreferencesStore()

/** Collected amount, in the selected payment (`collectCurrency`) currency. */
const amount = ref<number | undefined>()
const paymentMethod = ref('Cash')
const busy = ref(false)

/** Debt document currency — the payment always settles THIS currency. */
const debtCurrencyCode = computed(() => debtCurrency(props.debt, props.currency || preferences.currency || 'USD'))
/** Currency the cashier collects in (may differ from the debt currency). */
const collectCurrency = ref<'USD' | 'KHR'>('USD')
/** KHR per 1 USD used for the conversion (0 = not known yet). */
const collectRate = ref(0)
const rateDialogOpen = ref(false)
const pendingCollect = ref<'USD' | 'KHR' | null>(null)

/** Debt payments settle cash/bank — not new credit. */
const methodOptions = PAYMENT_METHODS.filter(method => method !== 'Credit')

const title = computed(() => props.kind === 'customer'
  ? t('app.reports.payCustomerDebtTitle')
  : t('app.reports.paySupplierDebtTitle'))
/** Documents behind the summary row (one row aggregates a party's open invoices). */
const invoiceCount = computed(() => {
  const debts = props.debt?.debts
  if (Array.isArray(debts)) return debts.length
  return props.debt?.id ? 1 : 0
})
const party = computed(() => {
  if (!props.debt) return ''
  return String(props.debt.customer || props.debt.supplier || '')
})
const original = computed(() => {
  const debt = props.debt
  if (!debt) return 0
  const explicit = debt.invoiceTotal ?? debt.totalAmount
  if (explicit != null) return Number(explicit)
  return Number(debt.paidAmount || 0) + Number(debt.remainingAmount || 0)
})
const paid = computed(() => Number(props.debt?.paidAmount || 0))
const remaining = computed(() => Number(props.debt?.remainingAmount || 0))
/** Collected in another currency than the debt's → convert at the rate. */
const converting = computed(() => collectCurrency.value !== debtCurrencyCode.value)
/** Amount this payment settles in the debt's own currency. */
const settledAmount = computed(() => {
  const entered = Number(amount.value || 0)
  if (!Number.isFinite(entered) || entered <= 0) return 0
  if (!converting.value) return roundMoney(entered)
  return convertAmount(entered, collectCurrency.value, debtCurrencyCode.value as 'USD' | 'KHR', collectRate.value)
})
const canSubmit = computed(() => Boolean(
  props.debt?.id
  && remaining.value > 0
  && settledAmount.value > 0
  && settledAmount.value <= remaining.value + 1e-9
  && paymentMethod.value,
))

/** Prefill the collected amount with the full outstanding balance. */
function prefillAmount() {
  if (remaining.value <= 0) {
    amount.value = undefined
    return
  }
  amount.value = converting.value
    ? convertAmount(remaining.value, debtCurrencyCode.value as 'USD' | 'KHR', collectCurrency.value, collectRate.value)
    : roundMoney(remaining.value)
}

watch(
  () => [open.value, props.debt?.id, props.kind] as const,
  ([isOpen]) => {
    if (!isOpen) return
    // Start collected in the debt's own currency; a KHR debt carries its
    // historical rate for a dollar collection.
    collectCurrency.value = debtCurrencyCode.value === 'KHR' ? 'KHR' : 'USD'
    collectRate.value = debtCurrencyCode.value === 'KHR' ? Number(props.debt?.exchangeRate || 0) : 0
    pendingCollect.value = null
    paymentMethod.value = 'Cash'
    prefillAmount()
  },
)

function money(value: unknown) {
  return formatMoney(value, debtCurrencyCode.value)
}

/** $/៛ pressed: collect in this currency (asking for the rate when needed). */
function selectCollectCurrency(value: 'USD' | 'KHR') {
  if (value === collectCurrency.value) return
  if (value !== debtCurrencyCode.value && collectRate.value <= 0) {
    pendingCollect.value = value
    rateDialogOpen.value = true
    return
  }
  collectCurrency.value = value
  prefillAmount()
}

/** Shared rate dialog confirmed: use it for this collection. */
function onRateConfirm(rate: number) {
  const parsed = Number(rate)
  if (!Number.isFinite(parsed) || parsed <= 0) return
  collectRate.value = parsed
  const target = pendingCollect.value
  pendingCollect.value = null
  if (target) {
    collectCurrency.value = target
    prefillAmount()
  }
}

async function onSubmit() {
  if (!canSubmit.value || !props.debt || busy.value) return
  const partyId = props.kind === 'customer'
    ? String(props.debt.customerId || '')
    : String(props.debt.supplierId || '')
  if (!partyId) return
  busy.value = true
  try {
    emit('submit', {
      kind: props.kind,
      partyId,
      amount: settledAmount.value,
      paymentMethod: paymentMethod.value,
      currency: debtCurrencyCode.value,
      collectedCurrency: collectCurrency.value,
      collectedAmount: roundMoney(Number(amount.value || 0)),
      exchangeRate: converting.value ? collectRate.value : null,
    })
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-hand-coins"
    color="success"
    size="sm"
    :loading="busy"
  >
    <div class="w-full space-y-3">
      <div class="grid gap-1 text-sm">
        <p>
          <span class="text-muted">{{ kind === 'customer' ? t('app.reports.customer') : t('app.reports.supplier') }}:</span>
          <span class="ms-1 font-medium">{{ party || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.openInvoices') }}:</span>
          <span class="ms-1 font-medium">{{ invoiceCount }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.originalAmount') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ money(original) }} ({{ debtCurrencyCode }})</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.paidAmount') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ money(paid) }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.remainingAmount') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ money(remaining) }}</span>
        </p>
      </div>

      <!-- Payment currency: the cashier collects in $ or ៛; the debt keeps its
           own document currency and is settled at the exchange rate. -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-muted">{{ t('app.reports.paymentCurrency') }}</span>
        <div class="inline-flex overflow-hidden rounded-sm border border-default">
          <UButton
            size="xs"
            :color="collectCurrency === 'USD' ? 'primary' : 'neutral'"
            :variant="collectCurrency === 'USD' ? 'solid' : 'ghost'"
            label="$"
            :title="t('app.pos.currencyUsd')"
            :aria-label="t('app.pos.currencyUsd')"
            :aria-pressed="collectCurrency === 'USD'"
            @click="selectCollectCurrency('USD')"
          />
          <UButton
            size="xs"
            :color="collectCurrency === 'KHR' ? 'primary' : 'neutral'"
            :variant="collectCurrency === 'KHR' ? 'solid' : 'ghost'"
            label="៛"
            :title="t('app.pos.currencyKhr')"
            :aria-label="t('app.pos.currencyKhr')"
            :aria-pressed="collectCurrency === 'KHR'"
            @click="selectCollectCurrency('KHR')"
          />
        </div>
      </div>

      <CommonAppMoneyField
        v-model="amount"
        name="amount"
        :label="t('app.reports.paymentAmount')"
        :required="true"
        :currency="collectCurrency"
        :min="0"
        :step="0.0001"
        class="w-full"
        :help="settledAmount > remaining ? t('app.reports.paymentOverRemaining') : ''"
      />
      <p v-if="converting && collectRate > 0" class="text-xs text-muted">
        = {{ money(settledAmount) }} ({{ debtCurrencyCode }}) · 1 USD = {{ formatNumber(Math.round(collectRate)) }} KHR
      </p>

      <CommonAppSelectMenuField
        v-model="paymentMethod"
        name="paymentMethod"
        :items="methodOptions.map(method => ({ label: method, value: method }))"
        :label="t('app.fields.paymentMethod')"
        :required="true"
        class="w-full"
      />
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="open = false"
        />
        <UButton
          color="success"
          icon="i-lucide-hand-coins"
          :loading="busy"
          :disabled="!canSubmit"
          :label="t('app.reports.confirmPayment')"
          @click="onSubmit"
        />
      </div>
    </template>
  </CommonAppDialog>

  <CommonAppExchangeRateDialog
    v-model:open="rateDialogOpen"
    @confirm="onRateConfirm"
  />
</template>
