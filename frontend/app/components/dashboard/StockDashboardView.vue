<script setup lang="ts">
import type { DateValue } from '@internationalized/date'
import type { EChartsCoreOption } from 'echarts/core'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { usePageSeo } from '~/composables/usePageSeo'
import { formatMoney } from '~/composables/module/useModule'
import { useFinanceRepository } from '~/repositories/index'
import type { DashboardSummary } from '~/repositories/contracts/entities'
import { datePickerPopoverContent, parsePickerValue, serializePickerValue } from '~/utils/date-picker'

/**
 * Stock & POS dashboard: exactly four KPI cards in one desktop row
 * (lg:grid-cols-4), an income/expense chart (date-filtered, auto-fit
 * height) and the complete Business Summary snapshot panel.
 */
const preferences = usePreferencesStore()
const financeRepository = useFinanceRepository()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()

onBeforeUnmount(clear)
usePageSeo({ title: () => t('app.pages.dashboard') })
watch(() => t('app.pages.dashboard'), (title) => {
  setTitle(title)
  setBreadcrumbs([{ label: title }])
}, { immediate: true })

const money = (value: unknown) => formatMoney(value, preferences.currency)

const serverSummary = ref<DashboardSummary | null>(null)
const chartSummary = ref<DashboardSummary | null>(null)
const summaryLoading = ref(false)
const chartLoading = ref(false)
const summaryError = ref<string | null>(null)

const now = new Date()
const pad2 = (n: number) => String(n).padStart(2, '0')
function monthBounds(date = new Date()) {
  const y = date.getFullYear()
  const m = date.getMonth()
  const last = new Date(y, m + 1, 0).getDate()
  return {
    start: `${y}-${pad2(m + 1)}-01`,
    end: `${y}-${pad2(m + 1)}-${pad2(last)}`,
  }
}

const initialMonth = monthBounds(now)
const chartDateStart = ref(initialMonth.start)
const chartDateEnd = ref(initialMonth.end)
const chartStartInput = useTemplateRef<{ inputsRef?: Array<{ $el?: HTMLElement }> } | null>('chartStartInput')
const chartEndInput = useTemplateRef<{ inputsRef?: Array<{ $el?: HTMLElement }> } | null>('chartEndInput')

function bindChartDate(model: Ref<string>) {
  return computed({
    get: () => parsePickerValue(model.value),
    set: (value: DateValue | null | undefined) => {
      const next = serializePickerValue(value)
      if (next) model.value = next
    },
  })
}

const chartStartValue = bindChartDate(chartDateStart)
const chartEndValue = bindChartDate(chartDateEnd)

async function loadServerSummary() {
  summaryLoading.value = true
  summaryError.value = null
  try {
    const { start, end } = monthBounds()
    serverSummary.value = await financeRepository.dashboard(start, end)
  }
  catch (error: unknown) {
    summaryError.value = error instanceof Error ? error.message : String(error)
  }
  finally {
    summaryLoading.value = false
  }
}

async function loadChartSummary() {
  chartLoading.value = true
  try {
    const { start, end } = chartRange.value
    chartSummary.value = await financeRepository.dashboard(start, end, 'dashboard-chart')
  }
  finally {
    chartLoading.value = false
  }
}

onMounted(() => {
  void loadServerSummary()
  void loadChartSummary()
})

const chartRange = computed(() => {
  const start = chartDateStart.value || initialMonth.start
  const end = chartDateEnd.value || initialMonth.end
  return { start, end }
})

watch([chartDateStart, chartDateEnd], () => {
  void loadChartSummary()
})

// Exactly four KPI cards (title + value only — no hint/description line).
const kpiCards = computed(() => {
  const summary = serverSummary.value
  return [
    {
      key: 'salesToday',
      title: t('app.dashboard.salesToday'),
      value: summary ? String(summary.salesToday) : '—',
    },
    {
      key: 'income',
      title: t('app.dashboard.income'),
      value: summary ? money(summary.income) : '—',
    },
    {
      key: 'expense',
      title: t('app.dashboard.expense'),
      value: summary ? money(summary.expense) : '—',
    },
    {
      key: 'debt',
      title: t('app.dashboard.outstandingDebt'),
      value: summary ? money(summary.customerDebt + summary.supplierDebt) : '—',
    },
  ]
})

const chartOption = computed<EChartsCoreOption>(() => {
  const summary = chartSummary.value
  const days = (summary?.incomeByDay || []).map(row => row.date.slice(5))
  const income = (summary?.incomeByDay || []).map(row => Number(row.amount || 0))
  const expense = (summary?.expenseByDay || []).map(row => Number(row.amount || 0))
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 6 },
    grid: { left: 8, right: 12, top: 16, bottom: 36, containLabel: true },
    xAxis: { type: 'category', data: days, boundaryGap: false },
    yAxis: { type: 'value', splitLine: { lineStyle: { opacity: 0.4 } } },
    series: [
      { name: t('app.dashboard.income'), type: 'line', smooth: true, showSymbol: false, data: income, lineStyle: { width: 2 }, areaStyle: { opacity: 0.08 } },
      { name: t('app.dashboard.expense'), type: 'line', smooth: true, showSymbol: false, data: expense, lineStyle: { width: 2 }, areaStyle: { opacity: 0.08 } },
    ],
  }
})

type SummaryRow = { label: string, value: string }

/**
 * Business Summary: the complete system snapshot (spec 2.1.1 / 5.5).
 * Values come from the month-to-date dashboard summary; “—” while loading.
 */
const summaryGroups = computed<Array<{ key: string, label: string, rows: SummaryRow[] }>>(() => {
  const summary = serverSummary.value
  const dash = '—'
  const row = (label: string, value?: string): SummaryRow => ({ label, value: summary ? value ?? dash : dash })
  return [
    {
      key: 'debts',
      label: t('app.dashboard.groupDebts'),
      rows: [
        row(t('app.dashboard.customerDebt'), summary ? money(summary.customerDebt) : undefined),
        row(t('app.dashboard.supplierDebt'), summary ? money(summary.supplierDebt) : undefined),
        row(t('app.dashboard.outstandingDebt'), summary ? money(summary.customerDebt + summary.supplierDebt) : undefined),
      ],
    },
    {
      key: 'stockHealth',
      label: t('app.dashboard.groupStockHealth'),
      rows: [
        row(t('app.dashboard.productsTotal'), summary ? String(summary.productsTotal) : undefined),
        row(t('app.dashboard.lowStock'), summary ? String(summary.lowStockCount) : undefined),
        row(t('app.dashboard.outOfStock'), summary ? String(summary.outOfStockCount) : undefined),
        row(t('app.dashboard.damageLoss'), summary ? money(summary.damageLoss) : undefined),
        row(t('app.dashboard.expiryLoss'), summary ? money(summary.expiryLoss) : undefined),
      ],
    },
    {
      key: 'operations',
      label: t('app.dashboard.groupOperations'),
      rows: [
        row(t('app.dashboard.pendingDeliveryNotes'), summary ? String(summary.pendingDeliveryNotes) : undefined),
      ],
    },
  ]
})

function refresh() {
  void loadServerSummary()
  void loadChartSummary()
}
</script>

<template>
  <div class="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
    <DashboardAppKpiSection :cards="kpiCards" :loading="summaryLoading" @refresh="refresh" />

    <div class="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-3">
      <UCard
class="min-w-0 lg:col-span-2"
        :ui="{ root: 'flex flex-col min-h-0', body: 'flex min-h-0 flex-1 flex-col p-3 sm:p-3' }">
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-sm font-medium text-highlighted">{{ t('app.dashboard.chartTitle') }}</p>
            <div class="flex items-center gap-1.5">
              <UInputDate
                ref="chartStartInput"
                v-model="chartStartValue"
                size="xs"
                color="neutral"
                variant="outline"
                :max-value="chartEndValue"
                :aria-label="t('app.fields.startDate')"
              >
                <template #trailing>
                  <UPopover
                    :reference="chartStartInput?.inputsRef?.[0]?.$el"
                    :content="datePickerPopoverContent"
                  >
                    <UButton
                      color="neutral"
                      variant="link"
                      size="xs"
                      icon="i-lucide-calendar"
                      class="px-0 text-muted"
                      :aria-label="t('app.fields.startDate')"
                    />
                    <template #content>
                      <UCalendar v-model="chartStartValue" class="p-2" :max-value="chartEndValue" />
                    </template>
                  </UPopover>
                </template>
              </UInputDate>
              <UIcon name="i-lucide-arrow-right" class="size-3.5 shrink-0 text-muted" />
              <UInputDate
                ref="chartEndInput"
                v-model="chartEndValue"
                size="xs"
                color="neutral"
                variant="outline"
                :min-value="chartStartValue"
                :aria-label="t('app.ui.date')"
              >
                <template #trailing>
                  <UPopover
                    :reference="chartEndInput?.inputsRef?.[0]?.$el"
                    :content="datePickerPopoverContent"
                  >
                    <UButton
                      color="neutral"
                      variant="link"
                      size="xs"
                      icon="i-lucide-calendar"
                      class="px-0 text-muted"
                      :aria-label="t('app.ui.date')"
                    />
                    <template #content>
                      <UCalendar v-model="chartEndValue" class="p-2" :min-value="chartStartValue" />
                    </template>
                  </UPopover>
                </template>
              </UInputDate>
            </div>
          </div>
        </template>
        <div v-if="chartLoading" class="grid min-h-[240px] flex-1 place-items-center text-sm text-muted">
          {{ t('common.loading') }}
        </div>
        <!-- min-h keeps the chart readable on stacked small screens; flex-1 fills
             the remaining viewport height on desktop (autoresize handles resizes). -->
        <div v-else class="min-h-[240px] flex-1">
          <DashboardAppEChart :option="chartOption" :aria-label="t('app.dashboard.chartTitle')" />
        </div>
      </UCard>

      <UCard class="min-w-0" :ui="{ root: 'flex flex-col min-h-0', body: 'flex min-h-0 flex-1 flex-col p-3 sm:p-3' }">
        <template #header>
          <p class="text-sm font-medium text-highlighted">{{ t('app.dashboard.summaryTitle') }}</p>
        </template>
        <p v-if="summaryError" class="text-xs text-error">{{ summaryError }}</p>
        <!-- Dense grouped rows; scrolls inside the panel when the list is long. -->
        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          <section v-for="group in summaryGroups" :key="group.key">
            <p class="mb-1 text-[11px] font-semibold tracking-wide text-dimmed uppercase">{{ group.label }}</p>
            <ul class="space-y-1.5">
              <li
v-for="row in group.rows"
:key="row.label"
                class="flex items-center justify-between gap-2 border-b border-default pb-1.5 text-sm last:border-0 last:pb-0">
                <span class="text-muted">{{ row.label }}</span>
                <span class="font-medium tabular-nums text-highlighted">{{ row.value }}</span>
              </li>
            </ul>
          </section>
        </div>
      </UCard>
    </div>
  </div>
</template>
