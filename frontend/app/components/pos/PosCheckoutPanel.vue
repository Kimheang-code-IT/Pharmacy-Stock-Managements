<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import { formatMoney } from '~/composables/module/useModule'
import { PAYMENT_METHODS } from '~/config/pos-options'
import type { PosCartLine } from '~/utils/pos/cart'
import { cartDiscountTotal, cartSubtotal, lineDiscountAmount, lineNet } from '~/utils/pos/cart'
import {
  checkoutDeliveryFee,
  checkoutDue,
  checkoutOutstanding,
  checkoutPaidNow,
  checkoutSaleNet,
  type CheckoutDebtRow,
} from '~/utils/pos/checkout'

const props = defineProps<{
  cart: PosCartLine[]
  currency: string
  /** Document currency of THIS sale (USD | KHR) + its applied rate. */
  saleCurrency: 'USD' | 'KHR'
  exchangeRate?: number
  /** USD → document-currency multiplier (1 for USD sales). */
  saleRate: number
  customerId?: string
  customerName: string
  customerPhone: string
  customerLocation: string
  /** Delivery destination (dialog-managed; prefilled from the customer). */
  deliveryPhone: string
  deliveryLocation: string
  paymentMethod: string
  paidInput?: number
  deliveryPrice: number
  needsDelivery: boolean
  depositInput: number
  includedDebtIds: string[]
  debts: CheckoutDebtRow[]
  customerOptions: Array<{
    label: string
    value: string
    phone?: string
    location?: string
    /** Secondary display line (phone · location) under the name. */
    description?: string
  }>
  canOperate: boolean
  completing?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:saleCurrency': [value: 'USD' | 'KHR']
  'update:exchangeRate': [value: number | undefined]
  'update:customerId': [value: string | undefined]
  'update:customerName': [value: string]
  'update:customerPhone': [value: string]
  'update:customerLocation': [value: string]
  'update:paymentMethod': [value: string]
  'update:paidInput': [value: number | undefined]
  'update:deliveryPrice': [value: number]
  'update:deliveryPhone': [value: string]
  'update:deliveryLocation': [value: string]
  'update:needsDelivery': [value: boolean]
  'update:depositInput': [value: number]
  'update:includedDebtIds': [value: string[]]
  back: []
  complete: []
}>()

const { t } = useI18n()
/** Display currency: the document currency for KHR sales, else the shop default. */
const displayCurrency = computed(() => props.saleCurrency === 'KHR' ? 'KHR' : props.currency)
/** Formats a USD-based amount (cart prices) in the document currency. */
const money = (value: unknown) => formatMoney(Number(value || 0) * props.saleRate, displayCurrency.value)
/** Formats an amount already expressed in the document currency. */
const moneyDoc = (value: unknown) => formatMoney(value, displayCurrency.value)
const fieldUi = { base: 'text-base' }

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const noEmptyDescription = ' '
const debtOpen = ref(false)
const deliveryInfoOpen = ref(false)
const customerCreateOpen = ref(false)

type CheckoutLineRow = Record<string, unknown> & {
  id: string
  lineNo: number
  productId: string
  name: string
  uom: string
  quantity: number
  unitPrice: number
  discountPercent: number
  discountAmount: number
  amount: number
}

const rows = computed<CheckoutLineRow[]>(() =>
  props.cart.map((line, index) => ({
    ...line,
    id: line.productId,
    lineNo: index + 1,
    discountAmount: lineDiscountAmount(line),
    amount: lineNet(line),
  })),
)

const columns = computed<TableColumn<CheckoutLineRow>[]>(() => [
  {
    accessorKey: 'lineNo',
    header: '#',
    enableSorting: false,
    meta: { class: { td: 'w-10 tabular-nums text-muted', th: 'w-10' } },
  },
  {
    accessorKey: 'name',
    header: t('app.pos.product'),
    enableSorting: false,
  },
  {
    accessorKey: 'uom',
    header: t('app.pos.uom'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap text-muted', th: '' } },
    cell: ({ row }) => String(row.original.uom || '—'),
  },
  {
    accessorKey: 'quantity',
    header: t('app.pos.qty'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
  },
  {
    accessorKey: 'unitPrice',
    header: t('app.pos.unitPrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => money(row.original.unitPrice),
  },
  {
    accessorKey: 'discountPercent',
    header: t('app.pos.discount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => {
      const percent = row.original.discountPercent || 0
      const amount = row.original.discountAmount
      return h('div', [
        h('span', `${percent}%`),
        amount
          ? h('span', { class: 'block text-xs text-muted' }, `−${money(amount)}`)
          : null,
      ])
    },
  },
  {
    accessorKey: 'amount',
    header: t('app.pos.amount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap font-medium', th: 'text-end' } },
    cell: ({ row }) => money(row.original.amount),
  },
])

const registeredCustomers = computed(() => props.customerOptions.filter(item => item.value))
const nameItems = computed(() => registeredCustomers.value)
const nameMenuValue = computed(() => props.customerId || undefined)

/** Search matches customer name, phone and location/address (spec §5.11):
 *  filter-fields drives the InputMenu's fuzzy filter across those keys. */
const customerFilterFields = ['label', 'phone', 'location', 'description']

/** The input shows the selected customer's name only. */
const selectedCustomerName = computed(() =>
  registeredCustomers.value.find(item => item.value === props.customerId)?.label
  || props.customerName
  || '')

/** Outstanding Debt field only shows when the selected customer has open
 *  debts (spec §5.11) — walk-in / debt-free customers see nothing here. */
const hasCustomerDebts = computed(() => customerDebtBalance.value > 0)

const subtotal = computed(() => cartSubtotal(props.cart))
const discountTotal = computed(() => cartDiscountTotal(props.cart))
const selectedDebts = computed(() =>
  props.debts.filter(row => props.includedDebtIds.includes(String(row.id))))
const appliedDeliveryPrice = computed(() =>
  checkoutDeliveryFee(props.needsDelivery, props.deliveryPrice))
// Cart amounts are USD-based and convert at the sale rate; delivery fee and
// deposit are typed in the document currency.
const saleNet = computed(() =>
  checkoutSaleNet(subtotal.value, discountTotal.value, 0) * props.saleRate
    + appliedDeliveryPrice.value)
const due = computed(() => checkoutDue(saleNet.value, Number(props.depositInput || 0)))
const paidNow = computed(() => checkoutPaidNow(props.paidInput, due.value, props.paymentMethod === 'Credit'))
const outstandingAmount = computed(() => checkoutOutstanding(due.value, paidNow.value))
const khrRateMissing = computed(() =>
  props.saleCurrency === 'KHR' && props.saleRate <= 0)
const outstandingDisplay = computed(() =>
  selectedDebts.value.length
    ? selectedDebts.value.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0)
    : customerDebtBalance.value)
/** Walk-in customers cannot leave an outstanding balance (spec §5.11),
 *  so the Credit tender is disabled until a registered customer is picked. */
const walkInCreditDisabled = computed(() => !props.customerId)
const canComplete = computed(() =>
  Boolean(props.cart.length)
  && props.canOperate
  && !props.disabled
  && !khrRateMissing.value
  && (outstandingAmount.value <= 0 || Boolean(props.customerId)))

const includedDebtIdsProxy = computed({
  get: () => props.includedDebtIds,
  set: (value: string[]) => emit('update:includedDebtIds', value),
})

const customerDebtBalance = computed(() =>
  props.debts.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0))

function onCustomerPick(value: unknown) {
  const selected = String(value ?? '')
  if (!selected) {
    emit('update:customerId', undefined)
    emit('update:customerName', '')
    emit('update:includedDebtIds', [])
    return
  }
  const option = registeredCustomers.value.find(item => item.value === selected)
  if (option?.value) {
    emit('update:customerId', option.value)
    emit('update:customerName', option.label)
  }
}

/** "Add new customer": opens the quick-create dialog (defaults to walk-in
 *  when nothing is picked); on save the new customer is auto-selected. */
function openCustomerCreate() {
  if (props.disabled) return
  customerCreateOpen.value = true
}

function onCustomerCreated(customerId: string) {
  const option = registeredCustomers.value.find(item => item.value === customerId)
  emit('update:customerId', customerId)
  emit('update:customerName', option?.label || '')
  emit('update:includedDebtIds', [])
}

function openDebts() {
  if (!props.customerId || props.disabled) return
  debtOpen.value = true
}

function emitDeliveryPrice(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:deliveryPrice', Number.isFinite(amount) ? Math.max(0, amount) : 0)
}

function emitDeposit(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:depositInput', Number.isFinite(amount) ? Math.max(0, amount) : 0)
}

function emitSaleCurrency(value: unknown) {
  emit('update:saleCurrency', value === 'KHR' ? 'KHR' : 'USD')
}
function emitExchangeRate(value: unknown) {
  const rate = value == null || value === '' ? undefined : Number(value)
  emit('update:exchangeRate', rate != null && Number.isFinite(rate) && rate > 0 ? rate : undefined)
}

function emitPaid(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:paidInput', Number.isFinite(amount) ? amount : undefined)
}

function onNeedsDelivery(value: unknown) {
  emit('update:needsDelivery', value === true)
  // Checking Delivery opens the delivery-info dialog (phone / location /
  // price for this invoice); unchecking keeps the entered values.
  if (value === true) deliveryInfoOpen.value = true
}
</script>

<template>
  <section class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 lg:flex-row">
    <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div class="flex shrink-0 items-center justify-between gap-3 px-1 pb-2">
        <UButton
          size="lg"
          color="neutral"
          variant="soft"
          icon="i-lucide-arrow-left"
          class="rounded-sm"
          :label="t('app.pos.backToCart')"
          @click="emit('back')"
        />
        <UCheckbox
          :model-value="needsDelivery"
          :label="t('app.pos.needsDelivery')"
          size="lg"
          :disabled="disabled"
          @update:model-value="onNeedsDelivery($event)"
        />
      </div>
      <TableAppListTable
        v-model:search="search"
        v-model:pagination="pagination"
        :data="rows"
        :columns="columns"
        :get-row-id="(row) => String(row.productId)"
        :empty-title="t('app.pos.emptyCart')"
        :empty-description="noEmptyDescription"
      />
    </div>

    <aside class="flex w-full shrink-0 flex-col overflow-y-auto lg:w-md xl:w-xl">
      <div class="rounded-sm border border-default bg-default p-4">
        <div class="grid gap-3">
          <UFormField
            :label="t('app.pos.customerName')"
            size="md"
          >
            <div class="flex gap-2">
              <UInputMenu
                :model-value="nameMenuValue"
                :items="nameItems"
                value-key="value"
                label-key="label"
                description-key="description"
                :filter-fields="customerFilterFields"
                :display-value="() => selectedCustomerName"
                open-on-click
                class="min-w-0 flex-1"
                size="lg"
                :ui="fieldUi"
                :placeholder="t('app.pos.customerSearchPlaceholder')"
                :search-input="true"
                :disabled="disabled"
                @update:model-value="onCustomerPick"
              />
              <UButton
                icon="i-lucide-user-plus"
                color="primary"
                variant="soft"
                size="lg"
                class="shrink-0"
                :title="t('app.pos.addNewCustomer')"
                :aria-label="t('app.pos.addNewCustomer')"
                :disabled="disabled"
                @click="openCustomerCreate"
              />
            </div>
            <p class="mt-1 text-xs text-muted">
              {{ t('app.pos.walkInDefaultHint') }}
            </p>
          </UFormField>
          <UFormField
            v-if="hasCustomerDebts"
            :label="t('app.debt.outstanding')"
            size="md"
          >
            <button
              type="button"
              class="flex min-h-10 w-full items-center justify-between rounded-sm bg-elevated/70 px-3 text-base"
              :disabled="disabled || !customerId || saleCurrency === 'KHR'"
              :title="saleCurrency === 'KHR' ? t('app.pos.debtUsdOnly') : undefined"
              @click="openDebts"
            >
              <span class="tabular-nums">{{ formatMoney(outstandingDisplay, currency) }}</span>
              <UIcon
                name="i-lucide-chevron-right"
                class="size-5 text-muted"
              />
            </button>
          </UFormField>

          <div class="space-y-1.5 border-t border-default pt-3 text-base">
            <div class="flex justify-between">
              <span class="text-muted">{{ t('app.pos.subtotal') }}</span>
              <span class="tabular-nums">{{ money(subtotal) }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-muted">{{ t('app.pos.discount') }}</span>
              <span class="tabular-nums">−{{ money(discountTotal) }}</span>
            </div>
          </div>

          <UFormField
            v-if="needsDelivery"
            :label="t('app.pos.deliveryInfoTitle')"
            size="md"
          >
            <button
              type="button"
              class="flex min-h-10 w-full items-center justify-between gap-2 rounded-sm bg-elevated/70 px-3 text-base"
              :disabled="disabled"
              @click="deliveryInfoOpen = true"
            >
              <span class="flex min-w-0 flex-col items-start leading-tight">
                <span class="truncate text-sm">{{ deliveryPhone || t('app.pos.deliveryPhone') }}</span>
                <span class="truncate text-xs text-muted">{{ deliveryLocation || t('app.pos.deliveryLocation') }}</span>
              </span>
              <span class="flex shrink-0 items-center gap-2">
                <span class="tabular-nums">{{ moneyDoc(deliveryPrice) }}</span>
                <UIcon
                  name="i-lucide-pencil"
                  class="size-4 text-muted"
                />
              </span>
            </button>
          </UFormField>

          <UFormField
            :label="t('app.pos.depositTotal')"
            size="md"
          >
            <UFieldGroup class="w-full">
              <UInputNumber
                :model-value="depositInput"
                :min="0"
                :step="0.01"
                :increment="false"
                :decrement="false"
                class="w-full"
                size="lg"
                :ui="{ base: 'text-base tabular-nums' }"
                :disabled="disabled || saleCurrency === 'KHR'"
                @update:model-value="emitDeposit($event)"
              />
              <UButton
                v-for="option in currencyOptions"
                :key="option.value"
                :label="option.symbol"
                :color="saleCurrency === option.value ? 'primary' : 'neutral'"
                :variant="saleCurrency === option.value ? 'soft' : 'outline'"
                size="lg"
                :disabled="disabled"
                :title="t(option.labelKey)"
                :aria-label="t(option.labelKey)"
                :aria-pressed="saleCurrency === option.value"
                @click="emitSaleCurrency(option.value)"
              />
            </UFieldGroup>
          </UFormField>

          <UFormField
            v-if="saleCurrency === 'KHR'"
            :label="t('app.pos.exchangeRate')"
            size="md"
          >
            <UInputNumber
              :model-value="exchangeRate"
              :min="1"
              :step="1"
              :increment="false"
              :decrement="false"
              class="w-full"
              size="lg"
              :ui="{ base: 'text-base tabular-nums' }"
              :placeholder="t('app.pos.exchangeRatePlaceholder')"
              :disabled="disabled"
              @update:model-value="emitExchangeRate($event)"
            />
          </UFormField>

          <UFormField
            :label="t('app.pos.paymentMethod')"
            size="md"
          >
            <USelect
              :model-value="paymentMethod"
              :items="canOperate ? [...PAYMENT_METHODS] : ['Cash']"
              class="w-full"
              size="lg"
              :disabled="disabled"
              @update:model-value="emit('update:paymentMethod', String($event))"
            />
            <p
              v-if="walkInCreditDisabled"
              class="mt-1 text-xs text-warning"
            >
              {{ t('app.pos.walkInCreditDisabled') }}
            </p>
          </UFormField>

          <UFormField
            :label="t('app.pos.paidNow')"
            size="md"
          >
            <UFieldGroup class="w-full">
              <UInputNumber
                :model-value="paidInput"
                :min="0"
                :max="due"
                :step="0.01"
                :increment="false"
                :decrement="false"
                class="w-full"
                size="lg"
                :ui="{ base: 'text-base tabular-nums' }"
                :placeholder="String(due.toFixed(2))"
                :disabled="disabled || paymentMethod === 'Credit'"
                @update:model-value="emitPaid($event)"
              />
              <UButton
                v-for="option in currencyOptions"
                :key="option.value"
                :label="option.symbol"
                :color="saleCurrency === option.value ? 'primary' : 'neutral'"
                :variant="saleCurrency === option.value ? 'soft' : 'outline'"
                size="lg"
                :disabled="disabled"
                :title="t(option.labelKey)"
                :aria-label="t(option.labelKey)"
                :aria-pressed="saleCurrency === option.value"
                @click="emitSaleCurrency(option.value)"
              />
            </UFieldGroup>
            <p
              v-if="paidInput == null"
              class="mt-1 text-xs text-muted"
            >
              {{ t('app.pos.paidNowDefaultHint') }}
            </p>
          </UFormField>

          <div class="flex justify-between border-t border-default pt-2 text-lg font-semibold">
            <span>{{ t('app.pos.outstandingAmount') }}</span>
            <span class="tabular-nums">{{ moneyDoc(outstandingAmount) }}</span>
          </div>

          <p
            v-if="outstandingAmount > 0"
            class="text-sm text-warning"
          >
            {{ t('app.pos.creditHint') }}
          </p>

          <UButton
            block
            color="primary"
            size="xl"
            :disabled="!canComplete"
            :loading="completing"
            :label="t('app.pos.submit')"
            @click="emit('complete')"
          />
        </div>
      </div>
    </aside>

    <PosOutstandingDebtDialog
      v-model:open="debtOpen"
      v-model:selected-ids="includedDebtIdsProxy"
      :debts="debts"
      :currency="currency"
    />

    <PosDeliveryInfoDialog
      v-model:open="deliveryInfoOpen"
      :customer-phone="customerPhone"
      :customer-location="customerLocation"
      :delivery-price="deliveryPrice"
      :disabled="disabled"
      @update:delivery-phone="emit('update:deliveryPhone', $event)"
      @update:delivery-location="emit('update:deliveryLocation', $event)"
      @update:delivery-price="emitDeliveryPrice"
    />

    <PosCustomerCreateDialog
      v-model:open="customerCreateOpen"
      :disabled="disabled"
      @created="onCustomerCreated"
    />
  </section>
</template>
