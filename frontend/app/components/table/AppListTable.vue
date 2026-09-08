<script setup lang="ts" generic="T extends Record<string, unknown>">
import type { TableColumn, TableRow } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { getPaginationRowModel } from '@tanstack/vue-table'
import type { DatePickerGranularity } from '~/utils/date-picker'
import { parsePageLimit, TABLE_PAGE_SIZES } from '~/utils/pagination'
import { listTableSelectedIds, listTableVirtualize } from '~/utils/table/list-table'
import { appTableFillUi } from '~/utils/table/theme'

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
})

const emit = defineEmits<{
  select: [event: Event, row: TableRow<T>]
}>()

const { t } = useI18n()

const paginationOptions = { getPaginationRowModel: getPaginationRowModel() }
const selectedIds = computed(() => listTableSelectedIds(rowSelection.value))
const total = computed(() => props.data.length)
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

          <slot name="actions" :selected-ids="selectedIds" />
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-hidden">
        <UTable
          v-if="total"
          v-model:global-filter="search"
          v-model:row-selection="rowSelection"
          v-model:pagination="pagination"
          :data="data"
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

