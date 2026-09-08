<script setup lang="ts">
import type { TableColumn, TableRow } from '@nuxt/ui'
import type { ModuleRelated } from '~/config/modules'
import type { AppRecord } from '~/config/admin-seed'
import { useModuleLabel } from '~/composables/module/useModule'
import { appTableUiCompact } from '~/utils/table/theme'

defineProps<{
  groups: Array<ModuleRelated & { rows: AppRecord[] }>
}>()

const { t } = useI18n()
const { relatedTitle } = useModuleLabel()

function titleOf(row: AppRecord) {
  return String(row.jobNo || row.quotationNo || row.debitNoteNo || row.documentNo || row.paymentNo || row.name || row.id)
}

const columns = computed<TableColumn<AppRecord>[]>(() => [
  {
    id: 'title',
    header: t('app.ui.record'),
    accessorFn: row => titleOf(row),
    enableSorting: false,
  },
  {
    accessorKey: 'status',
    header: t('app.ui.cols.status'),
    enableSorting: false,
    cell: ({ row }) => String(row.original.status || row.original.containerNo || row.original.date || '—'),
  },
])

function openRelated(path: string) {
  return (_event: Event, row: TableRow<AppRecord>) => {
    navigateTo(`${path}/${row.original.id}`)
  }
}
</script>

<template>
  <div class="space-y-6">
    <section v-for="group in groups" :key="group.path" class="space-y-2">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-medium text-highlighted">{{ relatedTitle(group) }}</h3>
        <UButton
size="xs"
color="neutral"
variant="ghost"
:to="group.path"
trailing-icon="i-lucide-arrow-up-right">
          {{ t('app.ui.viewAll') }}
        </UButton>
      </div>
      <div v-if="group.rows.length" class="overflow-x-auto">
        <UTable
:data="group.rows.slice(0, 20)"
:columns="columns"
          :get-row-id="(row: AppRecord) => row.id"
class="app-table app-table-compact min-w-max"
          :ui="appTableUiCompact"
@select="openRelated(group.path)" />
      </div>
      <div v-else class="rounded-sm border border-dashed border-default px-3 py-4 text-sm text-muted">
        {{ t('app.ui.noRelated') }}
      </div>
    </section>
  </div>
</template>

