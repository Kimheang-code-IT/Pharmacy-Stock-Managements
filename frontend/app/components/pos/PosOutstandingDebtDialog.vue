<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { formatMoney } from '~/composables/module/useModule'
import type { CheckoutDebtRow } from '~/utils/pos/checkout'

/**
 * Read-only history of the selected POS customer's open invoices. The cashier
 * enters how much of this debt is paid back on the checkout panel; rows are not
 * selectable here.
 */

const props = defineProps<{
  debts: CheckoutDebtRow[]
  currency: string
}>()

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const money = (value: unknown) => formatMoney(value, props.currency)

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const noEmptyDescription = ' '

watch(open, (value) => {
  if (!value) return
  search.value = ''
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
})

const columns = computed<TableColumn<CheckoutDebtRow>[]>(() => [
  {
    accessorKey: 'date',
    header: t('app.fields.date'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap text-muted', th: '' } },
  },
  {
    accessorKey: 'invoiceNo',
    header: t('app.fields.invoiceNo'),
    enableSorting: false,
    cell: ({ row }) => h('span', { class: 'font-medium' }, String(row.original.invoiceNo || '—')),
  },
  {
    accessorKey: 'paidAmount',
    header: t('app.pos.paidAmount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => money(row.original.paidAmount),
  },
  {
    accessorKey: 'remainingAmount',
    header: t('app.debt.outstanding'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => money(row.original.remainingAmount),
  },
  {
    accessorKey: 'paymentMethod',
    header: t('app.pos.paymentMethod'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap', th: '' } },
  },
])
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.debt.outstanding')"
    icon="i-lucide-hand-coins"
    wide
  >
    <div class="flex h-[60vh] max-h-[70vh] min-h-[55vh] min-w-0 flex-col overflow-hidden">
      <TableAppListTable
        v-model:search="search"
        v-model:pagination="pagination"
        :data="debts"
        :columns="columns"
        :get-row-id="(row) => String(row.id)"
        :empty-title="t('app.pos.emptyDebts')"
        :empty-description="noEmptyDescription"
      />
    </div>

    <template #footer>
      <div class="flex w-full justify-end">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('actions.close')"
          @click="open = false"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
