<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UCheckbox } from '#components'
import { h } from 'vue'
import { formatMoney } from '~/composables/module/useModule'
import { appTableCheckboxMeta } from '~/utils/table/theme'
import type { CheckoutDebtRow } from '~/utils/pos/checkout'

/**
 * Open invoices for the selected POS customer. Checking a row includes that
 * remaining debt on the current checkout invoice.
 */

const props = defineProps<{
  debts: CheckoutDebtRow[]
  currency: string
}>()

const open = defineModel<boolean>('open', { default: false })
const selectedIds = defineModel<string[]>('selectedIds', { default: () => [] })

const { t } = useI18n()
const money = (value: unknown) => formatMoney(value, props.currency)

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const noEmptyDescription = ' '

const selectedSet = computed(() => new Set(selectedIds.value))

function toggleIncluded(id: string, checked: boolean) {
  const next = new Set(selectedIds.value)
  if (checked) next.add(id)
  else next.delete(id)
  selectedIds.value = [...next]
}

watch(open, (value) => {
  if (!value) return
  search.value = ''
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
})

const columns = computed<TableColumn<CheckoutDebtRow>[]>(() => [
  {
    id: 'included',
    header: t('app.pos.includeOnInvoice'),
    enableSorting: false,
    meta: appTableCheckboxMeta,
    cell: ({ row }) => h(UCheckbox, {
      modelValue: selectedSet.value.has(String(row.original.id)),
      size: 'sm',
      'aria-label': t('app.pos.includeOnInvoice'),
      onClick: (event: Event) => event.stopPropagation(),
      'onUpdate:modelValue': (value: unknown) => {
        toggleIncluded(String(row.original.id), value === true)
      },
    }),
  },
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
