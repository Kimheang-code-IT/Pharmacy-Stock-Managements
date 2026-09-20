<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import { formatMoney } from '~/composables/module/useModule'
import { PAYMENT_METHODS } from '~/config/pos-options'
import type { PosCartLine } from '~/utils/pos/cart'
import type { PrintPaperSize } from '~/utils/print/html'
import { cartDiscountTotal, cartSubtotal, lineDiscountAmount, lineNet, roundMoney } from '~/utils/pos/cart'
import {
  checkoutDeliveryFee,
  checkoutDue,
  checkoutSaleNet,
  type CheckoutDebtRow,
} from '~/utils/pos/checkout'

const props = defineProps<{
  cart: PosCartLine[]
  /** Inherited from the cart: the ONE sale currency (USD | KHR). */
  saleCurrency: 'USD' | 'KHR'
  /** Shop default currency — used for debt records (kept in their own currency). */
  currency: string
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
  /** View-only: sale detail from Sales Report — no edits, Close instead of Submit. */
  viewMode?: boolean
  /** Return mode: the cart holds original-invoice lines to return. */
  returnMode?: boolean
  returnReason?: string
  returnRestock?: boolean
  /** Invoice paper size (A4 / A5) chosen on the keypad. */
  paperSize?: PrintPaperSize
}>()

const emit = defineEmits<{
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
  'update:returnReason': [value: string]
  'update:returnRestock': [value: boolean]
  'update:paperSize': [value: PrintPaperSize]
  back: []
  complete: []
  pay: [amount: number]
}>()

const { t } = useI18n()
/** Every checkout amount is in the inherited sale currency — no conversion. */
const money = (value: unknown) => formatMoney(Number(value || 0), props.saleCurrency)
const fieldUi = { base: 'text-base' }

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const noEmptyDescription = ' '
const debtOpen = ref(false)
const deliveryInfoOpen = ref(false)
const customerCreateOpen = ref(false)
/** When true the right block is replaced by the amount-paid keypad. */
const paying = ref(false)

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
    accessorKey: 'discountAmount',
    header: t('app.pos.discount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => {
      const amount = row.original.discountAmount || 0
      return h('span', { class: amount ? 'text-end tabular-nums' : 'text-end tabular-nums text-muted' },
        amount ? `−${money(amount)}` : '—')
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

const subtotal = computed(() => cartSubtotal(props.cart))
const discountTotal = computed(() => cartDiscountTotal(props.cart))
const appliedDeliveryPrice = computed(() =>
  checkoutDeliveryFee(props.needsDelivery, props.deliveryPrice))
// Sale amounts only — deposit / prior-debt payment is settled separately.
const grandTotal = computed(() =>
  checkoutSaleNet(subtotal.value, discountTotal.value, appliedDeliveryPrice.value))
const due = computed(() => checkoutDue(grandTotal.value))
const returnTotal = computed(() => grandTotal.value)
const canComplete = computed(() =>
  Boolean(props.cart.length)
  && props.canOperate
  && !props.disabled
  && (!props.returnMode || Boolean(String(props.returnReason || '').trim())))

const returnReasonProxy = computed({
  get: () => String(props.returnReason || ''),
  set: (value: string) => emit('update:returnReason', value),
})
const returnRestockProxy = computed({
  get: () => props.returnRestock !== false,
  set: (value: boolean) => emit('update:returnRestock', value === true),
})

const includedDebtIdsProxy = computed({
  get: () => props.includedDebtIds,
  set: (value: string[]) => emit('update:includedDebtIds', value),
})

/** Paper size for the post-sale invoice print (A4 / A5) chosen on the keypad. */
const paperSizeModel = computed<PrintPaperSize>({
  get: () => props.paperSize ?? 'A4',
  set: value => emit('update:paperSize', value),
})

const customerDebtBalance = computed(() =>
  props.debts.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0))
/** Customer has open invoices — shows the Debt button + prior-debt amount input. */
const hasCustomerDebts = computed(() => customerDebtBalance.value > 0)
/** Debt button is a toggle: on when the customer's invoices are included. */
const debtActive = computed(() => props.includedDebtIds.length > 0)

/** Prior-debt amount auto-fills from the selected invoices (still editable). */
const selectedDebtTotal = computed(() => roundMoney(
  props.debts
    .filter(row => props.includedDebtIds.includes(String(row.id)))
    .reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0),
))

watch(selectedDebtTotal, (total) => {
  emit('update:depositInput', total)
})

function emitDeposit(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:depositInput', Number.isFinite(amount) ? Math.max(0, amount) : 0)
}

/** Debt toggle: activate selects invoices (dialog), deactivate clears them. */
function toggleDebt() {
  if (props.disabled) return
  if (debtActive.value) {
    emit('update:includedDebtIds', [])
    return
  }
  openDebts()
}

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

function onNeedsDelivery(value: unknown) {
  emit('update:needsDelivery', value === true)
  // Checking Delivery opens the delivery-info dialog (phone / location /
  // price for this invoice); unchecking keeps the entered values.
  if (value === true) deliveryInfoOpen.value = true
}

/** Next: swap the right block for the inline amount-paid keypad. */
function startPayment() {
  if (!canComplete.value) return
  paying.value = true
}

function onKeypadConfirm(amount: number) {
  emit('pay', amount)
}

// Leave the keypad once the sale/cart is cleared (successful submit).
watch(() => props.cart.length, (length) => {
  if (!length) paying.value = false
})
</script>

<template>
  <section class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 lg:flex-row">
    <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div
        v-if="returnMode"
        class="flex shrink-0 items-center justify-end gap-3 px-1 pb-2"
      >
        <div class="inline-flex items-center gap-2 rounded-sm bg-warning/10 px-3 py-1 text-sm font-medium text-warning">
          <UIcon name="i-lucide-undo-2" class="size-4" />
          {{ t('app.pos.returnMode') }}
        </div>
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
      <div class="flex min-h-full flex-col gap-3 rounded-sm border border-default bg-default p-4">
        <PosPaymentKeypad
          v-if="!returnMode && paying"
          v-model:paper-size="paperSizeModel"
          :total="due"
          :delivery-price="appliedDeliveryPrice"
          :currency="saleCurrency"
          :payment-method="paymentMethod"
          :busy="completing"
          :disabled="disabled"
          @confirm="onKeypadConfirm"
          @cancel="paying = false"
        />
        <div v-else-if="returnMode" class="grid gap-3">
          <UFormField
            :label="t('app.pos.customerName')"
            size="md"
          >
            <p class="text-base font-medium">
              {{ customerName || t('app.pos.walkIn') }}
            </p>
          </UFormField>

          <div class="flex justify-between border-t border-default pt-3 text-base">
            <span class="text-muted">{{ t('app.reports.returnTotal') }}</span>
            <span class="font-semibold tabular-nums">{{ money(returnTotal) }}</span>
          </div>

          <UFormField
            :label="t('app.reports.returnReason')"
            size="md"
            required
          >
            <UTextarea
              v-model="returnReasonProxy"
              :rows="3"
              class="w-full"
              :disabled="disabled"
            />
          </UFormField>

          <div class="border-t border-default pt-3">
            <UCheckbox
              v-model="returnRestockProxy"
              :label="t('app.reports.restock')"
              :disabled="disabled"
            />
            <p class="mt-1 text-xs text-muted">
              {{ t('app.pos.returnRestockHint') }}
            </p>
          </div>

          <div class="flex gap-2">
            <UButton
              class="flex-1"
              color="neutral"
              variant="soft"
              size="xl"
              icon="i-lucide-arrow-left"
              :label="t('app.pos.backToCart')"
              @click="emit('back')"
            />
            <UButton
              class="flex-1"
              color="warning"
              size="xl"
              :disabled="!canComplete"
              :loading="completing"
              :label="t('app.reports.confirmReturn')"
              @click="emit('complete')"
            />
          </div>
        </div>
        <div v-else class="flex flex-1 flex-col gap-6">
          <!-- Top: Delivery / Debt / Add customer on one line. -->
          <div class="grid grid-cols-3 gap-2">
            <UButton
              block
              size="lg"
              :color="needsDelivery ? 'error' : 'neutral'"
              variant="solid"
              icon="i-lucide-truck"
              :label="t('app.pos.needsDelivery')"
              :disabled="disabled"
              @click="onNeedsDelivery(!needsDelivery)"
            />
            <UButton
              block
              size="lg"
              :color="debtActive ? 'error' : 'neutral'"
              variant="solid"
              icon="i-lucide-wallet"
              :label="`${t('app.pos.debt')} · ${formatMoney(customerDebtBalance, currency)}`"
              :disabled="disabled || !customerId || saleCurrency === 'KHR' || !hasCustomerDebts"
              @click="toggleDebt"
            />
            <UButton
              block
              size="lg"
              color="primary"
              variant="solid"
              icon="i-lucide-user-plus"
              :label="t('app.pos.addCustomer')"
              :disabled="disabled"
              @click="openCustomerCreate"
            />
          </div>

          <UFormField
            :label="t('app.pos.customerName')"
            size="md"
          >
            <UInputMenu
              :model-value="nameMenuValue"
              :items="nameItems"
              value-key="value"
              label-key="label"
              description-key="description"
              :filter-fields="customerFilterFields"
              :display-value="() => selectedCustomerName"
              open-on-click
              class="w-full"
              size="lg"
              :ui="fieldUi"
              :placeholder="t('app.pos.customerSearchPlaceholder')"
              :search-input="true"
              :disabled="disabled"
              @update:model-value="onCustomerPick"
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
          </UFormField>

          <UFormField
            v-if="hasCustomerDebts"
            :label="t('app.pos.depositTotal')"
            size="md"
          >
            <CommonAppMoneyField
              inline
              :model-value="depositInput"
              :currency="saleCurrency"
              :min="0"
              :step="0.01"
              class="w-full"
              size="lg"
              align="right"
              :disabled="disabled || saleCurrency === 'KHR'"
              @update:model-value="emitDeposit($event)"
            />
          </UFormField>

          <!-- Bottom: Total, then Back / Next. -->
          <div class="mt-auto grid gap-3">
            <div class="flex justify-between border-t border-default pt-3 text-lg font-semibold">
              <span>{{ t('app.pos.total') }}</span>
              <span class="tabular-nums">{{ money(due) }}</span>
            </div>

            <!-- Back + Next on one line, full width of the right block. -->
            <div class="flex gap-2">
              <UButton
                class="h-14 flex-1 justify-center"
                color="neutral"
                variant="soft"
                size="xl"
                icon="i-lucide-arrow-left"
                :label="t('app.pos.backToCart')"
                @click="emit('back')"
              />
              <UButton
                v-if="viewMode"
                class="h-14 flex-1 justify-center"
                color="neutral"
                variant="soft"
                size="xl"
                :label="t('common.close')"
                @click="emit('back')"
              />
              <UButton
                v-else
                class="h-14 flex-1 justify-center"
                color="primary"
                size="xl"
                icon="i-lucide-arrow-right"
                trailing
                :disabled="!canComplete"
                :label="t('app.pos.next')"
                @click="startPayment"
              />
            </div>
          </div>
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
      :currency="saleCurrency"
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
