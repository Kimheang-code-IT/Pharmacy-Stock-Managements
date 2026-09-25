<script setup lang="ts" generic="T extends Record<string, unknown>">
import type { TableColumn, TableRow, DropdownMenuItem } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { getPaginationRowModel } from '@tanstack/vue-table'
import type { DatePickerGranularity } from '~/utils/date-picker'
import { parsePageLimit, TABLE_PAGE_SIZES } from '~/utils/pagination'
import { listTableSelectedIds, listTableVirtualize } from '~/utils/table/list-table'
import { appTableFillUi } from '~/utils/table/theme'
import { isDateFieldKey, isDateTimeFieldKey, isNumericKey } from '~/utils/module/field-keys'
import { normalizeTimestampInput } from '~/utils/format/format-service'

export type ListTableEmptyAction = {
  icon?: string
  label: string
  onClick: () => void
}

const search = defineModel<string>('search', { default: '' })
const dateStart = defineModel<string>('dateStart', { default: '' })
const dateEnd = defineModel<string>('dateEnd', { default: '' })
const rowSelection = defineModel<Record<string, boolean>>('rowSelection', { default: () => ({}) })
const pagination = defineModel<PaginationState>('pagination', {
  default: () => ({ pageIndex: 0, pageSize: 20 }),
})

const props = withDefaults(defineProps<{
  data: T[]
  columns: TableColumn<T>[]
  loading?: boolean
  getRowId?: (row: T) => string
  searchPlaceholder?: string
  showDateRange?: boolean
  dateLabel?: string
  dateGranularity?: DatePickerGranularity
  /** Lights the mobile filter button when any toolbar filter or date range is set. */
  filtersActive?: boolean
  emptyIcon?: string
  emptyTitle?: string
  emptyDescription?: string
  emptyActions?: ListTableEmptyAction[]
  /** Show the toolbar sort menu (derived from the table's own columns). */
  sortable?: boolean
}>(), {
  loading: false,
  getRowId: (row: T) => String(row.id || ''),
  searchPlaceholder: '',
  showDateRange: false,
  dateLabel: '',
  dateGranularity: 'day',
  filtersActive: false,
  emptyIcon: 'i-lucide-inbox',
  emptyTitle: '',
  emptyDescription: '',
  emptyActions: () => [],
  sortable: true,
})

const emit = defineEmits<{
  select: [event: Event, row: TableRow<T>]
}>()

const { t } = useI18n()

/* --------------------------------- sorting -------------------------------- */
// Client-side sort menu derived from the table's own columns. Date columns
// offer oldest/newest, numeric + document-number columns offer smallest/
// largest, the rest A→Z / Z→A. Header click-sorting stays disabled — the
// toolbar icon is the only sort affordance.
type SortKind = 'date' | 'number' | 'text'
type SortOption = { key: string, label: string, kind: SortKind }

const MEDIA_KEY = /image|avatar|photo|logo|icon|file/i

function sortKindFor(key: string): SortKind {
  if (isDateTimeFieldKey(key) || isDateFieldKey(key) || /(^|_)date$/i.test(key) || /At$/.test(key)) return 'date'
  if (isNumericKey(key)) return 'number'
  if (/total|amount|price|qty|quantity|count|balance|debt|stock|discount|paid|due|cost|value|rate|length/i.test(key)) return 'number'
  // Document / sequence numbers ("Sale No", "Next Number Preview", codes…).
  const lower = key.toLowerCase()
  if (/(no|number|code|reference|preview)$/.test(lower) || /number|sequence|seqno/.test(lower)) return 'number'
  return 'text'
}

const sortOptions = computed<SortOption[]>(() => {
  if (!props.sortable) return []
  const seen = new Set<string>()
  const options: SortOption[] = []
  for (const column of props.columns) {
    const rawKey = 'accessorKey' in column ? column.accessorKey : undefined
    const key = typeof rawKey === 'string' ? rawKey : ''
    if (!key || seen.has(key) || key.startsWith('__') || MEDIA_KEY.test(key)) continue
    if (typeof column.header !== 'string' || !column.header.trim()) continue
    seen.add(key)
    options.push({ key, label: column.header, kind: sortKindFor(key) })
  }
  return options
})

const sortKey = ref('')
const sortDesc = ref(false)
const sortActive = computed(() => sortOptions.value.some(option => option.key === sortKey.value))

function ascLabel(option: SortOption) {
  if (option.kind === 'date') return t('app.ui.sortOldest')
  if (option.kind === 'number') return t('app.ui.sortSmallest')
  return t('app.ui.sortAsc')
}

function descLabel(option: SortOption) {
  if (option.kind === 'date') return t('app.ui.sortNewest')
  if (option.kind === 'number') return t('app.ui.sortLargest')
  return t('app.ui.sortDesc')
}

function applySort(key: string, desc: boolean) {
  sortKey.value = key
  sortDesc.value = desc
}

function clearSort() {
  sortKey.value = ''
  sortDesc.value = false
}

// Drop a stale sort when the columns change (e.g. switching pages/modules).
watch(sortOptions, (options) => {
  if (sortKey.value && !options.some(option => option.key === sortKey.value)) clearSort()
})

function compareSortValues(a: unknown, b: unknown, key: string): number {
  const emptyA = a == null || a === ''
  const emptyB = b == null || b === ''
  if (emptyA || emptyB) return emptyA && emptyB ? 0 : (emptyA ? -1 : 1)
  if (sortKindFor(key) === 'date') {
    const at = Date.parse(normalizeTimestampInput(String(a)))
    const bt = Date.parse(normalizeTimestampInput(String(b)))
    if (!Number.isNaN(at) && !Number.isNaN(bt)) return at - bt
  }
  const an = typeof a === 'number' ? a : Number(a)
  const bn = typeof b === 'number' ? b : Number(b)
  if (!Number.isNaN(an) && !Number.isNaN(bn)) return an - bn
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

const sortedData = computed<T[]>(() => {
  if (!sortActive.value) return props.data
  const key = sortKey.value
  const factor = sortDesc.value ? -1 : 1
  return [...props.data].sort((a, b) => factor * compareSortValues(a[key], b[key], key))
})

const sortMenuItems = computed<DropdownMenuItem[][]>(() => {
  if (!sortOptions.value.length) return []
  const fields: DropdownMenuItem[] = sortOptions.value.map(option => ({
    label: option.label,
    icon: sortActive.value && sortKey.value === option.key
      ? (sortDesc.value ? 'i-lucide-arrow-down' : 'i-lucide-arrow-up')
      : 'i-lucide-arrows-up-down',
    children: [[
      { label: ascLabel(option), onSelect: () => applySort(option.key, false) },
      { label: descLabel(option), onSelect: () => applySort(option.key, true) },
    ]],
  }))
  const groups: DropdownMenuItem[][] = [fields]
  if (sortActive.value) {
    groups.push([{ label: t('app.ui.sortClear'), icon: 'i-lucide-x', onSelect: clearSort }])
  }
  return groups
})

const paginationOptions = { getPaginationRowModel: getPaginationRowModel() }
const selectedIds = computed(() => listTableSelectedIds(rowSelection.value))
const total = computed(() => sortedData.value.length)
const virtualize = computed(() => listTableVirtualize(total.value, pagination.value.pageSize))
const searchPlaceholderText = computed(() => props.searchPlaceholder || t('app.ui.search'))
const dateLabelText = computed(() => props.dateLabel || t('app.ui.date'))
const emptyTitleText = computed(() => props.emptyTitle || t('app.ui.noRecords'))
const emptyDescriptionText = computed(() => props.emptyDescription || t('app.ui.noRecordsHint'))
const pageSizeItems = TABLE_PAGE_SIZES.map(value => ({ label: String(value), value: String(value) }))

function rowId(row: T) {
  return props.getRowId(row)
}

function setPageSize(value: unknown) {
  pagination.value = { pageIndex: 0, pageSize: parsePageLimit(value, 20) }
}

function setPage(page: number) {
  pagination.value = { ...pagination.value, pageIndex: Math.max(0, page - 1) }
}

function onSelect(event: Event, row: TableRow<T>) {
  emit('select', event, row)
}
</script>

<template>
  <div class="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden px-1.5 pt-1.5 pb-0">
    <div class="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-sm border border-default bg-default shadow-xs">
      <div class="flex items-center gap-3 border-b border-default px-2 py-2">
        <CommonAppLiveSearch
          v-model="search"
          class="w-56 shrink-0 sm:w-64"
          :placeholder="searchPlaceholderText"
        />

        <div class="flex min-w-0 flex-1 items-center justify-end gap-2 overflow-x-auto">
          <CommonAppFilterMenu :active="filtersActive" class="min-w-0">
            <template #default="{ compact }">
              <slot name="filters" :compact="compact" />
              <CommonAppDateRangeFilter
                v-if="showDateRange"
                v-model:start="dateStart"
                v-model:end="dateEnd"
                :granularity="dateGranularity"
                :inline="compact"
                :label="dateLabelText"
              />
            </template>
          </CommonAppFilterMenu>

          <UDropdownMenu
            v-if="sortOptions.length"
            :items="sortMenuItems"
            :content="{ align: 'end' }"
          >
            <UButton
              color="neutral"
              :variant="sortActive ? 'soft' : 'outline'"
              size="sm"
              icon="i-lucide-arrow-up-down"
              :class="sortActive ? 'text-primary' : ''"
              :aria-label="t('app.ui.sort')"
              :title="t('app.ui.sort')"
            />
          </UDropdownMenu>

          <slot name="actions" :selected-ids="selectedIds" />
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-hidden">
        <UTable
          v-if="total"
          v-model:global-filter="search"
          v-model:row-selection="rowSelection"
          v-model:pagination="pagination"
          :data="sortedData"
          :columns="columns"
          :loading="loading"
          :get-row-id="rowId"
          :pagination-options="paginationOptions"
          :virtualize="virtualize"
          sticky="header"
          class="app-table h-full min-h-0"
          :ui="appTableFillUi"
          @select="onSelect"
        />
        <UEmpty
          v-else
          variant="naked"
          :icon="emptyIcon"
          :title="emptyTitleText"
          :description="emptyDescriptionText"
          :actions="emptyActions.length ? emptyActions : undefined"
          class="py-16"
        />
      </div>

      <div class="flex items-center justify-between gap-2 border-t border-default px-2 py-1.5">
        <div class="flex items-center gap-1.5">
          <span class="text-[11px] leading-none text-muted">{{ t('common.rowsPerPage') }}</span>
          <USelect
            :model-value="String(pagination.pageSize)"
            :items="pageSizeItems"
            size="xs"
            class="w-16"
            @update:model-value="setPageSize"
          />
        </div>
        <UPagination
          :page="pagination.pageIndex + 1"
          :items-per-page="pagination.pageSize"
          :total="total"
          size="xs"
          :sibling-count="1"
          @update:page="setPage"
        />
      </div>
    </div>
  </div>
</template>

