<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UBadge } from '#components'
import { h } from 'vue'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useCurrencyRateDialog } from '~/composables/common/useCurrencyRateDialog'
import { usePageSeo } from '~/composables/usePageSeo'
import { formatMoney } from '~/composables/module/useModule'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'
import { PAYMENT_METHODS } from '~/config/pos-options'
import { downloadTableExport, type ExportTableColumn } from '~/utils/export/table'
import type { ExportRequest } from '~/types/stock-pos/export'
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'
import { useFinanceRepository } from '~/repositories/index'
import type { FinanceEntry, FinanceEntryType, FinanceSummary } from '~/repositories/contracts/entities'

definePageMeta({ titleKey: 'app.pages.financeReport', permission: 'report.finance' })

/**
 * Finance Report (spec: Finance Report section): an operational income &
 * expense **table** — no chart here (Dashboard keeps its own chart).
 *
 * - AppHeader chrome: title + breadcrumbs + Add Expense only (no date range,
 *   no Refresh — filters live on the table toolbar).
 * - Income rows are system-derived from confirmed POS sales / paid amounts.
 * - Expense rows come from the Add Expense modal (no /expenses page).
 * - Net Result subtracts recorded operating expenses.
 */
const preferences = usePreferencesStore()
const auth = useAuthStore()
const { localization, formatDate } = useAppLocalization()
const financeRepository = useFinanceRepository()
const toast = useToast()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()

onBeforeUnmount(clear)
usePageSeo({ title: () => t('app.pages.financeReport') })
watch(() => t('app.pages.financeReport'), (title) => {
  setTitle(title)
  setBreadcrumbs([
    { label: t('app.nav.reports') },
    { label: title },
  ])
}, { immediate: true })

/** Spec: gate Add Expense behind the expense permission (hidden when denied). */
const canCreateExpense = computed(() => auth.canAccessPage('expense.create'))

const money = (value: unknown) => formatMoney(value, preferences.currency)
const loading = ref(false)
const error = ref<string | null>(null)
const entries = ref<FinanceEntry[]>([])
const summary = ref<FinanceSummary | null>(null)

/* ------------------------------ filters (table toolbar) --------------- */

const q = ref('')
const typeFilter = ref<string[]>([])
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const now = new Date()
const pad2 = (n: number) => String(n).padStart(2, '0')
const monthBounds = (date = now) => {
  const y = date.getFullYear()
  const m = date.getMonth()
  const last = new Date(y, m + 1, 0).getDate()
  return { start: `${y}-${pad2(m + 1)}-01`, end: `${y}-${pad2(m + 1)}-${pad2(last)}` }
}
const initial = monthBounds()
const dateStart = ref(initial.start)
const dateEnd = ref(initial.end)

const typeFilterItems = computed(() => [
  { label: t('app.finance.typeIncome'), value: 'income' },
  { label: t('app.finance.typeExpense'), value: 'expense' },
])

const filteredEntries = computed(() => {
  if (!typeFilter.value.length) return entries.value
  return entries.value.filter(row => typeFilter.value.includes(row.type))
})

const tableRows = computed<FinanceRow[]>(() =>
  filteredEntries.value.map(row => row as FinanceRow))

const filtersActive = computed(() => typeFilter.value.length > 0)

/* ------------------------------ summary cards ------------------------- */
/*
 * Two explicit, never-confused views (spec: separate P&L from cash flow):
 * - Profit & Loss is the accounting view; supplier payments never appear here
 *   because inventory cost is already recognized through COGS.
 * - Cash Flow counts only money that actually moved (paid sales, collections,
 *   paid refunds, supplier payments, expenses).
 */

const plCards = computed(() => {
  const pl = summary.value?.profitAndLoss
  return [
    { key: 'netSales', label: t('app.finance.netSales'), value: money(pl?.netSales ?? 0) },
    { key: 'cogs', label: t('app.finance.costOfGoodsSold'), value: money(pl?.costOfGoodsSold ?? 0) },
    { key: 'grossProfit', label: t('app.finance.grossProfit'), value: money(pl?.grossProfit ?? 0) },
    { key: 'operatingProfit', label: t('app.finance.operatingProfit'), value: money(pl?.operatingProfit ?? 0) },
  ]
})

const cashCards = computed(() => {
  const cf = summary.value?.cashFlow
  return [
    { key: 'cashIn', label: t('app.finance.cashIn'), value: money(cf?.totalInflow ?? 0) },
    { key: 'cashOut', label: t('app.finance.cashOut'), value: money(cf?.totalOutflow ?? 0) },
    { key: 'netCashFlow', label: t('app.finance.netCashFlow'), value: money(cf?.netCashFlow ?? 0) },
    { key: 'outstanding', label: t('app.finance.outstanding'), value: money(summary.value?.outstanding ?? 0) },
  ]
})

/* ------------------------------ data loading -------------------------- */

async function load() {
  loading.value = true
  error.value = null
  try {
    const [rows, summaryData] = await Promise.all([
      financeRepository.entries(dateStart.value, dateEnd.value),
      financeRepository.financeSummary(dateStart.value, dateEnd.value),
    ])
    entries.value = rows
    summary.value = summaryData
  }
  catch (err: unknown) {
    error.value = err instanceof Error ? err.message : String(err)
  }
  finally {
    loading.value = false
  }
}

onMounted(load)
// Reload happens when filters change or after Add Expense — never via a
// header Refresh control (spec: header holds title + breadcrumbs + Add Expense).
watch([dateStart, dateEnd], load)

/* ------------------------------ table columns ------------------------- */

/** Table row type: keeps AppListTable's `Record<string, unknown>` constraint. */
type FinanceRow = FinanceEntry & Record<string, unknown>

const typeBadge = (type: FinanceEntryType) => ({
  income: { color: 'success' as const, label: t('app.finance.typeIncome') },
  expense: { color: 'warning' as const, label: t('app.finance.typeExpense') },
})[type]

const columns = computed<TableColumn<FinanceRow>[]>(() => {
  // Reference the localization format so the table re-renders when the
  // Date format changes in Settings > Localization.
  void localization.value.dateFormat
  return [
    {
      accessorKey: 'date',
      header: t('app.fields.date'),
      enableSorting: false,
      meta: { class: { td: 'whitespace-nowrap', th: '' } },
      cell: ({ row }) => h('span', { class: 'whitespace-nowrap text-default' }, formatDate(row.original.date)),
    },
    {
      accessorKey: 'type',
      header: t('app.fields.type'),
      enableSorting: false,
      cell: ({ row }) => {
        const badge = typeBadge(row.original.type)
        return h(UBadge, { color: badge.color, variant: 'subtle', size: 'sm' }, () => badge.label)
      },
    },
    {
      accessorKey: 'reference',
      header: t('app.finance.referenceCategory'),
      enableSorting: false,
      cell: ({ row }) => h('span', {
        class: 'block max-w-44 truncate text-default',
        title: row.original.type === 'income' ? row.original.reference : row.original.category,
      }, row.original.type === 'income'
        ? (row.original.reference || '—')
        : (row.original.category || '—')),
    },
    {
      accessorKey: 'description',
      header: t('app.fields.description'),
      enableSorting: false,
      cell: ({ row }) => h('span', {
        class: 'block max-w-64 truncate text-muted',
        title: row.original.description,
      }, row.original.description || '—'),
    },
    {
      accessorKey: 'amount',
      header: t('app.fields.amount'),
      enableSorting: false,
      meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
      cell: ({ row }) => h('span', { class: 'font-medium' }, formatMoney(row.original.amount, row.original.currency)),
    },
    {
      accessorKey: 'paymentMethod',
      header: t('app.fields.paymentMethod'),
      enableSorting: false,
      cell: ({ row }) => h('span', { class: 'whitespace-nowrap text-default' }, row.original.paymentMethod || '—'),
    },
    {
      accessorKey: 'user',
      header: t('app.fields.user'),
      enableSorting: false,
      cell: ({ row }) => h('span', { class: 'whitespace-nowrap text-default' }, row.original.user || '—'),
    },
  ]
})

/* ------------------------------ export (Excel / PDF) ------------------ */

const exporting = ref(false)
const exportFields = computed(() =>
  columns.value
    .map(column => ({
      label: String(column.header || ''),
      value: 'accessorKey' in column ? String(column.accessorKey || '') : '',
    }))
    .filter(field => field.value))

async function onExport(request: ExportRequest) {
  if (exporting.value) return
  exporting.value = true
  try {
    const codes = request.fieldCodes?.length ? request.fieldCodes : exportFields.value.map(field => field.value)
    const cols = exportFields.value
      .filter(field => codes.includes(field.value))
      .map((field): ExportTableColumn => ({
        key: field.value,
        label: field.label,
        type: field.value === 'date' ? 'date' : field.value === 'amount' ? 'money' : 'text',
      }))
    let rows = filteredEntries.value as unknown as Array<Record<string, unknown>>
    if (request.startDate) rows = rows.filter(row => String(row.date || '') >= request.startDate!)
    if (request.endDate) rows = rows.filter(row => String(row.date || '') <= request.endDate!)
    const data = rows.map((row) => {
      const out: Record<string, unknown> = {}
      for (const column of cols) {
        if (column.key === 'reference') out[column.key] = row.reference || row.category || ''
        else if (column.key === 'amount') out[column.key] = Number(row.amount || 0)
        else if (column.key === 'date') out[column.key] = String(row.date || '').slice(0, 10)
        else out[column.key] = row[column.key] ?? ''
      }
      return out
    })
    await downloadTableExport({
      title: t('app.pages.financeReport'),
      format: request.format,
      columns: cols,
      rows: data,
      subtitle: request.startDate || request.endDate
        ? `${request.startDate || '…'} → ${request.endDate || '…'}`
        : null,
    })
    toast.add({ title: t('core.exportDialog.exported', { n: data.length }), color: 'success' })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('core.exportDialog.exportFailed'),
        description: apiErrorMessage(error, t('core.exportDialog.exportFailed')),
        color: 'error',
      })
    }
  }
  finally {
    exporting.value = false
  }
}

/* ------------------------------ Add Expense modal --------------------- */

const EXPENSE_CATEGORIES = ['Utilities', 'Rent', 'Salaries', 'Supplies', 'Transport', 'Marketing', 'Other'] as const
/** Credit is a sales-side method; expenses are settled directly. */
const expensePaymentMethods = PAYMENT_METHODS.filter(method => method !== 'Credit')

const addExpenseOpen = ref(false)
const addExpenseBusy = ref(false)
const expenseForm = reactive({
  date: initial.end,
  category: '',
  description: '',
  amount: undefined as number | undefined,
  paymentMethod: '',
  reference: '',
  currency: 'USD' as 'USD' | 'KHR',
  exchangeRate: undefined as number | undefined,
})

const canSubmitExpense = computed(() => Boolean(
  expenseForm.date
  && expenseForm.category
  && Number(expenseForm.amount || 0) > 0
  && expenseForm.paymentMethod
  && (expenseForm.currency !== 'KHR' || Number(expenseForm.exchangeRate || 0) > 0),
))

/** Shared toggle logic: switching the expense to KHR asks for the exchange
 *  rate through the shared dialog; cancelling keeps USD. */
const {
  dialogOpen: expenseRateDialogOpen,
  toggle: toggleExpenseCurrency,
  confirm: confirmExpenseExchangeRate,
} = useCurrencyRateDialog({
  currency: computed({
    get: () => expenseForm.currency,
    set: value => { expenseForm.currency = value },
  }),
  rate: computed({
    get: () => expenseForm.exchangeRate,
    set: value => { expenseForm.exchangeRate = value },
  }),
})

/** Convert the entered amount when the document currency switches so the
 *  value keeps its worth (USD→KHR multiply; KHR→USD divide by the rate). */
function convertExpenseAmount(from: 'USD' | 'KHR', to: 'USD' | 'KHR', rate: number) {
  const amount = Number(expenseForm.amount || 0)
  if (from === to || !amount || !(rate > 0)) return
  const converted = from === 'USD' ? amount * rate : amount / rate
  expenseForm.amount = Math.round(converted * 100) / 100
}

/** Currency toggle from the amount field: convert once the new rate is known. */
function onExpenseCurrencySelect(value: 'USD' | 'KHR') {
  const from = expenseForm.currency
  const knownRate = Number(expenseForm.exchangeRate || 0)
  toggleExpenseCurrency(value)
  if (expenseForm.currency !== from) {
    convertExpenseAmount(from, expenseForm.currency, Number(expenseForm.exchangeRate || knownRate))
  }
}

/** Rate dialog confirmed: apply it, then convert the amount to KHR. */
function onExpenseRateConfirm(rate: number) {
  const from = expenseForm.currency
  confirmExpenseExchangeRate(rate)
  convertExpenseAmount(from, expenseForm.currency, rate)
}

function openAddExpense() {
  expenseForm.date = new Date().toISOString().slice(0, 10)
  expenseForm.category = ''
  expenseForm.description = ''
  expenseForm.amount = undefined
  expenseForm.paymentMethod = ''
  expenseForm.reference = ''
  expenseForm.currency = 'USD'
  expenseForm.exchangeRate = undefined
  addExpenseOpen.value = true
}

async function submitExpense() {
  if (!canSubmitExpense.value || addExpenseBusy.value) return
  addExpenseBusy.value = true
  try {
    await financeRepository.createExpense({
      date: expenseForm.date,
      category: expenseForm.category,
      description: expenseForm.description,
      amount: Number(expenseForm.amount),
      paymentMethod: expenseForm.paymentMethod,
      reference: expenseForm.reference || null,
      currency: expenseForm.currency,
      exchangeRate: expenseForm.currency === 'KHR' ? Number(expenseForm.exchangeRate || 0) : 1,
    })
    addExpenseOpen.value = false
    await load()
    toast.add({ title: t('app.finance.expenseSaved'), color: 'success' })
  }
  catch (err: unknown) {
    toast.add({
      title: t('app.finance.expenseFailed'),
      description: err instanceof Error ? err.message : String(err),
      color: 'error',
    })
  }
  finally {
    addExpenseBusy.value = false
  }
}
</script>

<template>
  <div class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/20">
    <LayoutAppHeaderPageActions
      :can-create="canCreateExpense"
      :can-export="true"
      :export-fields="exportFields"
      :exporting="exporting"
      :show-refresh="false"
      :create-label="t('app.finance.addExpense')"
      :refreshing="loading"
      @create="openAddExpense"
      @export="onExport"
    />

    <div class="flex flex-col gap-3 px-3 pt-2">
      <p v-if="error" class="text-sm text-error">{{ error }}</p>

      <section class="space-y-1.5">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">
          {{ t('app.finance.profitAndLoss') }}
        </h3>
        <div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <UCard v-for="card in plCards" :key="card.key" :ui="{ body: 'p-3 sm:p-3' }">
            <p class="text-xs text-muted">{{ card.label }}</p>
            <p class="mt-1 text-lg font-semibold tabular-nums">{{ card.value }}</p>
          </UCard>
        </div>
      </section>

      <section class="space-y-1.5">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-muted">
          {{ t('app.finance.cashFlow') }}
        </h3>
        <div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <UCard v-for="card in cashCards" :key="card.key" :ui="{ body: 'p-3 sm:p-3' }">
            <p class="text-xs text-muted">{{ card.label }}</p>
            <p class="mt-1 text-lg font-semibold text-default tabular-nums">{{ card.value }}</p>
          </UCard>
        </div>
      </section>
    </div>

    <TableAppListTable
      v-model:search="q"
      v-model:date-start="dateStart"
      v-model:date-end="dateEnd"
      v-model:pagination="pagination"
      :data="tableRows"
      :columns="columns"
      :loading="loading"
      :show-date-range="true"
      :date-label="t('app.ui.date')"
      :filters-active="filtersActive"
      :search-placeholder="t('app.finance.searchPlaceholder')"
      :empty-icon="canCreateExpense ? 'i-lucide-plus' : 'i-lucide-inbox'"
      :empty-title="t('app.finance.empty')"
      :empty-description="t('app.finance.emptyHint')"
      :empty-actions="canCreateExpense
        ? [{ icon: 'i-lucide-plus', label: t('app.finance.addExpense'), onClick: openAddExpense }]
        : []"
    >
      <template #filters="{ compact }">
        <CommonAppFilterSelect
          v-model="typeFilter"
          :items="typeFilterItems"
          :placeholder="t('app.finance.filterType')"
          :class="compact ? 'w-full' : 'w-36'"
        />
      </template>
    </TableAppListTable>

    <CommonAppDialog
      v-model:open="addExpenseOpen"
      :title="t('app.finance.addExpense')"
      icon="i-lucide-plus"
      size="sm"
      :loading="addExpenseBusy"
    >
      <div class="w-full space-y-3">
        <CommonAppDateField
          v-model="expenseForm.date"
          :label="t('app.fields.date')"
          :required="true"
          granularity="day"
          class="w-full"
        />
        <CommonAppSelectMenuField
          v-model="expenseForm.category"
          :items="[...EXPENSE_CATEGORIES]"
          :label="t('app.finance.category')"
          :placeholder="t('app.finance.categoryPlaceholder')"
          :required="true"
          class="w-full"
        />
        <CommonAppTextField
          v-model="expenseForm.description"
          :label="t('app.fields.description')"
          class="w-full"
        />
        <CommonAppMoneyField
          v-model="expenseForm.amount"
          currency-toggle
          :currency="expenseForm.currency"
          :label="t('app.fields.amount')"
          :required="true"
          :min="0"
          :step="0.01"
          :help="Number(expenseForm.amount || 0) <= 0 ? t('app.finance.amountPositive') : ''"
          class="w-full"
          @update:currency="onExpenseCurrencySelect"
        />
        <CommonAppSelectMenuField
          v-model="expenseForm.paymentMethod"
          :items="[...expensePaymentMethods]"
          :label="t('app.fields.paymentMethod')"
          :placeholder="t('app.finance.paymentMethodPlaceholder')"
          :required="true"
          class="w-full"
        />
        <CommonAppMoneyField
          v-if="expenseForm.currency === 'KHR'"
          v-model="expenseForm.exchangeRate"
          :label="t('app.pos.exchangeRate')"
          :min="1"
          :step="1"
          :placeholder="t('app.pos.exchangeRatePlaceholder')"
          class="w-full"
        />
        <CommonAppTextField
          v-model="expenseForm.reference"
          :label="t('app.finance.referenceOptional')"
          class="w-full"
        />
      </div>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            :label="t('common.cancel')"
            @click="addExpenseOpen = false"
          />
          <UButton
            icon="i-lucide-plus"
            :loading="addExpenseBusy"
            :disabled="!canSubmitExpense"
            :label="t('app.finance.addExpense')"
            @click="submitExpense"
          />
        </div>
      </template>
    </CommonAppDialog>

    <!-- Shared KHR exchange-rate dialog: opened by the amount currency toggle. -->
    <CommonAppExchangeRateDialog
      v-model:open="expenseRateDialogOpen"
      @confirm="onExpenseRateConfirm"
    />
  </div>
</template>
