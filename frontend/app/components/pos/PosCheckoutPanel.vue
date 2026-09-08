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
  checkoutSaleNet,
  type CheckoutDebtRow,
} from '~/utils/pos/checkout'

const props = defineProps<{
  cart: PosCartLine[]
  currency: string
  customerId?: string
  customerName: string
  customerPhone: string
  customerLocation: string
  paymentMethod: string
  paidInput?: number
  deliveryPrice: number
  needsDelivery: boolean
  depositInput: number
  includedDebtIds: string[]
  debts: CheckoutDebtRow[]
  customerOptions: Array<{ label: string, value: string }>
  canOperate: boolean
  completing?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:customerId': [value: string | undefined]
  'update:customerName': [value: string]
  'update:customerPhone': [value: string]
  'update:customerLocation': [value: string]
  'update:paymentMethod': [value: string]
  'update:paidInput': [value: number | undefined]
  'update:deliveryPrice': [value: number]
  'update:needsDelivery': [value: boolean]
  'update:depositInput': [value: number]
  'update:includedDebtIds': [value: string[]]
  back: []
  complete: []
}>()

const { t } = useI18n()
const money = (value: unknown) => formatMoney(value, props.currency)
const fieldUi = { base: 'text-base' }

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const noEmptyDescription = ' '
const debtOpen = ref(false)

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
const nameItems = computed(() => {
  const items = registeredCustomers.value
  const name = props.customerName.trim()
  if (!props.customerId && name && !items.some(item => item.label === name || item.value === name)) {
    return [...items, { label: name, value: name }]
  }
  return items
})
const nameMenuValue = computed(() => props.customerId || props.customerName.trim() || undefined)

const subtotal = computed(() => cartSubtotal(props.cart))
const discountTotal = computed(() => cartDiscountTotal(props.cart))
const selectedDebts = computed(() =>
  props.debts.filter(row => props.includedDebtIds.includes(String(row.id))))
const appliedDeliveryPrice = computed(() =>
  checkoutDeliveryFee(props.needsDelivery, props.deliveryPrice))
const saleNet = computed(() =>
  checkoutSaleNet(subtotal.value, discountTotal.value, appliedDeliveryPrice.value))
const due = computed(() => checkoutDue(saleNet.value, Number(props.depositInput || 0)))
const paidNow = computed(() => Number(props.paidInput ?? 0))
const outstandingAmount = computed(() => checkoutOutstanding(due.value, paidNow.value))
const customerDebtBalance = computed(() =>
  props.debts.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0))
const outstandingDisplay = computed(() =>
  selectedDebts.value.length
    ? selectedDebts.value.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0)
    : customerDebtBalance.value)
const canComplete = computed(() =>
  Boolean(props.cart.length)
  && props.canOperate
  && !props.disabled
  && (outstandingAmount.value <= 0 || Boolean(props.customerId)))

const includedDebtIdsProxy = computed({
  get: () => props.includedDebtIds,
  set: (value: string[]) => emit('update:includedDebtIds', value),
})

function onCreateCustomer(name: string) {
  const next = name.trim()
  emit('update:customerId', undefined)
  emit('update:customerName', next)
  emit('update:includedDebtIds', [])
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
    emit('update:customerName', option.label.split(' · ')[0] || option.label)
    return
  }
  emit('update:customerId', undefined)
  emit('update:customerName', selected)
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

function emitPaid(value: unknown) {
  const amount = value == null || value === '' ? 0 : Number(value)
  emit('update:paidInput', Number.isFinite(amount) ? amount : undefined)
}

function onNeedsDelivery(value: unknown) {
  emit('update:needsDelivery', value === true)
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
            <UInputMenu
              :model-value="nameMenuValue"
              :items="nameItems"
              value-key="value"
              create-item
              open-on-click
              class="w-full"
              size="lg"
              :ui="fieldUi"
              :placeholder="t('app.pos.walkIn')"
              :disabled="disabled"
              @create="onCreateCustomer"
              @update:model-value="onCustomerPick"
            />
          </UFormField>
          <UFormField
            :label="t('app.pos.customerPhone')"
            size="md"
          >
            <UInput
              :model-value="customerPhone"
              class="w-full"
              size="lg"
              :ui="fieldUi"
              placeholder="012 xxx xxx"
              :disabled="disabled"
              @update:model-value="emit('update:customerPhone', String($event ?? ''))"
            />
          </UFormField>
          <UFormField
            :label="t('app.pos.location')"
            size="md"
          >
            <UInput
              :model-value="customerLocation"
              class="w-full"
              size="lg"
              :ui="fieldUi"
              :placeholder="t('app.pos.locationPlaceholder')"
              :disabled="disabled"
              @update:model-value="emit('update:customerLocation', String($event ?? ''))"
            />
          </UFormField>
          <UFormField
            :label="t('app.debt.outstanding')"
            size="md"
          >
            <button
              type="button"
              class="flex min-h-10 w-full items-center justify-between rounded-sm bg-elevated/70 px-3 text-base"
              :disabled="disabled || !customerId"
              @click="openDebts"
            >
              <span class="tabular-nums">{{ money(outstandingDisplay) }}</span>
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
            :label="t('app.pos.deliveryPrice')"
            size="md"
          >
            <UInputNumber
              :model-value="deliveryPrice"
              :min="0"
              :step="0.01"
              :increment="false"
              :decrement="false"
              class="w-full"
              size="lg"
              :ui="{ base: 'text-base tabular-nums' }"
              :disabled="disabled"
              @update:model-value="emitDeliveryPrice($event)"
            />
          </UFormField>

          <UFormField
            :label="t('app.pos.depositTotal')"
            size="md"
          >
            <UInputNumber
              :model-value="depositInput"
              :min="0"
              :step="0.01"
              :increment="false"
              :decrement="false"
              class="w-full"
              size="lg"
              :ui="{ base: 'text-base tabular-nums' }"
              :disabled="disabled"
              @update:model-value="emitDeposit($event)"
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
            :label="t('app.pos.paidNow')"
            size="md"
          >
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
          </UFormField>

          <div class="flex justify-between border-t border-default pt-2 text-lg font-semibold">
            <span>{{ t('app.pos.outstandingAmount') }}</span>
            <span class="tabular-nums">{{ money(outstandingAmount) }}</span>
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
  </section>
</template>
