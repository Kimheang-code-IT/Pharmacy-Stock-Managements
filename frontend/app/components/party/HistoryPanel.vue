<script setup lang="ts">
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UBadge } from '#components'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import { formatMoney } from '~/composables/module/useModule'
import { usePartyLedger } from '~/composables/party/usePartyLedger'
import { apiErrorMessage } from '~/utils/api/errors'
import { listTableRowMetaColumn } from '~/utils/table/list-columns'
import { partyDay, type PartyHistory, type PartyKind } from '~/utils/party/ledger'

/**
 * Customer **Sales History** / Supplier **Purchase History** tab.
 * Reads the party-scoped history endpoints and shows backend totals only.
 */
const props = withDefaults(defineProps<{
  party?: AppRecord | null
  kind?: PartyKind
  reloadKey?: number
}>(), {
  party: null,
  kind: 'customer',
  reloadKey: 0,
})

const { t } = useI18n()
const auth = useAuthStore()
const preferences = usePreferencesStore()
const ledger = usePartyLedger()

const canEdit = computed(() => props.kind === 'customer'
  ? auth.canAccessPage('pos.sale_edit')
  : auth.canAccessPage('stock.in'))

/** Return-all reuses the POS / Purchase return flows (reverse + restock). */
const canReturn = computed(() => props.kind === 'customer'
  ? auth.canAccessPage('pos.return')
  : auth.canAccessPage('stock.in'))

/** Reprint the sales invoice (customer history only — purchase history has none). */
const canPrint = computed(() => props.kind === 'customer'
  && auth.canAccessPage('pos.print'))

const showActions = computed(() => canEdit.value || canReturn.value || canPrint.value)

const printOpen = ref(false)
const printSaleId = ref('')

const rows = ref<PartyHistory[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
const search = ref('')
const dateStart = ref('')
const dateEnd = ref('')
const statusFilter = ref('All')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })

const partyId = computed(() => String(props.party?.id || ''))

async function load() {
  if (!partyId.value) {
    rows.value = []
    return
  }
  loading.value = true
  loadError.value = null
  try {
    rows.value = await ledger.listHistory(props.kind, partyId.value)
  }
  catch (error: unknown) {
    loadError.value = apiErrorMessage(error, t('api.somethingWentWrong'))
    rows.value = []
  }
  finally {
    loading.value = false
  }
}

watch(() => [partyId.value, props.kind, props.reloadKey] as const, () => void load(), { immediate: true })

/** Status filter options: every status present on the loaded rows + "All". */
const statusItems = computed(() => {
  const statuses = [...new Set(rows.value
    .map(row => String(row.status || '').trim())
    .filter(Boolean))]
    .sort((a, b) => a.localeCompare(b))
  return [
    { label: t('app.pos.allCategories'), value: 'All' },
    ...statuses.map(status => ({ label: status, value: status })),
  ]
})

function inDateRange(value: unknown): boolean {
  const day = partyDay(value)
  if (!day) return !dateStart.value && !dateEnd.value
  if (dateStart.value && day < dateStart.value) return false
  if (dateEnd.value && day > dateEnd.value) return false
  return true
}

const filteredRows = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return rows.value
    .filter(row => statusFilter.value === 'All' || String(row.status || '') === statusFilter.value)
    .filter(row => inDateRange(row.date))
    .filter((row) => {
      if (!needle) return true
      return [row.documentNo, row.status, row.user]
        .map(value => String(value ?? '').toLowerCase())
        .some(value => value.includes(needle))
    })
})

function money(value: unknown, currency = preferences.currency) {
  return formatMoney(value, currency)
}

const columns = computed<TableColumn<PartyHistory & Record<string, unknown>>[]>(() => {
  const supplier = props.kind === 'supplier'
  const base: TableColumn<PartyHistory & Record<string, unknown>>[] = [
    {
      accessorKey: 'documentNo',
      header: supplier ? t('app.reports.purchaseNo') : t('app.fields.invoiceNo'),
      enableSorting: false,
      cell: ({ row }) => h('span', { class: 'font-medium whitespace-nowrap' }, row.original.documentNo || '—') as never,
    },
    {
      accessorKey: 'date',
      header: t('app.fields.date'),
      enableSorting: false,
      cell: ({ row }) => h('span', { class: 'text-muted whitespace-nowrap' }, partyDay(row.original.date) || '—') as never,
    },
    {
      accessorKey: 'total',
      header: t('app.fields.total'),
      enableSorting: false,
      meta: { class: { td: 'text-end tabular-nums', th: 'text-end' } },
      cell: ({ row }) => h('span', {}, money(row.original.total, row.original.currency)) as never,
    },
  ]
  base.push(
    {
      accessorKey: 'paidAmount',
      header: t('app.reports.paidAmount'),
      enableSorting: false,
      meta: { class: { td: 'text-end tabular-nums', th: 'text-end' } },
      cell: ({ row }) => h('span', {}, money(row.original.paidAmount, row.original.currency)) as never,
    },
    {
      accessorKey: 'debtAmount',
      header: t('app.reports.remainingAmount'),
      enableSorting: false,
      meta: { class: { td: 'text-end tabular-nums font-medium', th: 'text-end' } },
      cell: ({ row }) => h('span', {}, money(row.original.debtAmount, row.original.currency)) as never,
    },
  )
  base.push(
    {
      accessorKey: 'user',
      header: t('app.fields.user'),
      enableSorting: false,
      cell: ({ row }) => h('span', { class: 'text-muted whitespace-nowrap' }, row.original.user || '—') as never,
    },
    {
      accessorKey: 'status',
      header: t('app.fields.status'),
      enableSorting: false,
      cell: ({ row }) => h(UBadge, { color: 'neutral', variant: 'subtle', size: 'sm' }, () => row.original.status || '—') as never,
    },
  )
  if (showActions.value) {
    base.push(listTableRowMetaColumn<PartyHistory & Record<string, unknown>>({
      summary: '',
      items: row => rowMenu(row as PartyHistory),
    }))
  }
  return base
})

/** Row actions reuse the original transaction screen (POS / Purchase): Edit
 *  loads the invoice and saving reverse-applies it; Return loads every line
 *  into the return flow with restock enabled. */
function rowMenu(row: PartyHistory): DropdownMenuItem[][] {
  if (!row.id) return []
  const items: DropdownMenuItem[] = []
  if (canPrint.value) {
    items.push({
      label: t('app.reports.printInvoice'),
      icon: 'i-lucide-printer',
      onSelect: () => {
        printSaleId.value = row.id
        printOpen.value = true
      },
    })
  }
  if (canEdit.value) {
    const to = props.kind === 'customer'
      ? `/pos?editSaleId=${encodeURIComponent(row.id)}`
      : `/reports/purchases/new?editPurchaseId=${encodeURIComponent(row.id)}&purchaseNo=${encodeURIComponent(row.documentNo)}`
    items.push({
      label: t('app.reports.edit'),
      icon: 'i-lucide-pencil',
      color: 'primary',
      onSelect: () => { void navigateTo(to) },
    })
  }
  if (canReturn.value) {
    const to = props.kind === 'customer'
      ? `/pos?returnSaleId=${encodeURIComponent(row.id)}`
      : `/reports/purchases/new?returnPurchaseId=${encodeURIComponent(row.id)}&purchaseNo=${encodeURIComponent(row.documentNo)}`
    items.push({
      label: t('app.reports.returnAll'),
      icon: 'i-lucide-undo-2',
      color: 'warning',
      onSelect: () => { void navigateTo(to) },
    })
  }
  return items.length ? [items] : []
}
</script>

<template>
  <!-- Fit the viewport so the table fills the height and only the rows scroll
       (sticky header + footer); viewport units keep it responsive on all
       devices. Mirrors the shared BatchListPanel / QtyHistoryDialog pattern. -->
  <div class="flex h-[60vh] max-h-[70vh] min-h-[55vh] min-w-0 flex-col overflow-hidden">
    <p v-if="loadError" class="px-3 pt-2 text-sm text-error">{{ loadError }}</p>
    <TableAppListTable
      v-model:search="search"
      v-model:pagination="pagination"
      v-model:date-start="dateStart"
      v-model:date-end="dateEnd"
      :data="filteredRows"
      :columns="columns"
      :loading="loading"
      show-date-range
      :date-label="t('app.fields.date')"
      :filters-active="statusFilter !== 'All'"
      :empty-title="t('app.ui.noRecords')"
    >
      <template #filters>
        <USelect
          v-model="statusFilter"
          :items="statusItems"
          value-key="value"
          size="sm"
          class="w-36"
          :aria-label="t('app.fields.status')"
        />
      </template>
    </TableAppListTable>

    <CommonAppInvoicePrintDialog
      v-model:open="printOpen"
      :sale-id="printSaleId"
    />
  </div>
</template>
