<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import { h, type Component } from 'vue'
import { CommonAppInputDate, UButton, UCheckbox, UDropdownMenu, UIcon, UInput, UInputNumber, USelect } from '#components'
import type { ModuleLineColumn, ModuleTable } from '~/config/modules'
import { useModuleLabel } from '~/composables/module/useModule'
import type { DatePickerGranularity } from '~/utils/date-picker'
import { fileTableRowBy, fileTableRowCreated, fileTableRowName, filePreviewHref, revokeFilePreview, useFileAttachments } from '~/utils/module/attachments'
import { fileTypeIcon } from '~/utils/file-icon'
import { formatDate, formatDateTime, formatMoney, formatNumber } from '~/utils/format/format-service'
import { appTableUiCompactReadonly, appTableUiLine } from '~/utils/table/theme'

const props = withDefaults(defineProps<{
  table: ModuleTable
  modelValue: Array<Record<string, unknown>>
  disabled?: boolean
  compact?: boolean
  viewOnlyActions?: boolean
}>(), {
  compact: false,
})

const emit = defineEmits<{
  'update:modelValue': [Array<Record<string, unknown>>]
  'rowAction': [action: 'view', row: Record<string, unknown>]
}>()

const { t, te } = useI18n()
const { fieldLabel, tableTitle } = useModuleLabel()
const { inputRef, openPicker, rowsFromInput } = useFileAttachments()

function setFileInput(element: unknown) {
  inputRef.value = element as HTMLInputElement | null
}

const TableButton = UButton as Component
const TableCheckbox = UCheckbox as Component
const TableDate = CommonAppInputDate as Component
const TableIcon = UIcon as Component
const TableInput = UInput as Component
const TableInputNumber = UInputNumber as Component
const TableMenu = UDropdownMenu as Component
const TableSelect = USelect as Component

const isFileTable = computed(() => props.table.kind === 'files' || props.table.key === 'attachments')
const cellSize = computed(() => props.compact ? 'xs' : 'sm')
const tableUi = computed(() => props.compact ? appTableUiCompactReadonly : appTableUiLine)

const moneyKeys = new Set(['unitPrice', 'discountPercent', 'taxPercent', 'discountAmount', 'discount', 'taxAmount', 'lineTotal', 'total', 'amount'])
const numericKeys = new Set(['quantity', 'actualQuantity', 'remaining', 'netWeightKg', 'grossWeightKg', 'weightKg', 'taxRate', ...moneyKeys])

function columnCellClass(column: ModuleLineColumn) {
  if (column.key === 'blNo' || column.key === 'truckNo' || column.key === 'containerNo') return 'w-36 min-w-28'
  if (column.key === 'quantity' || column.key === 'actualQuantity' || column.key === 'remaining') return 'w-20 min-w-20 text-right tabular-nums'
  if (column.key === 'unit') return 'w-24 min-w-24'
  if (column.key === 'discountPercent' || column.key === 'taxPercent' || column.key === 'taxRate') return 'w-24 min-w-24 text-right tabular-nums'
  if (column.key === 'netWeightKg' || column.key === 'grossWeightKg' || column.key === 'weightKg') {
    return column.inlineFields?.length ? 'w-36 min-w-32 text-right tabular-nums' : 'w-28 min-w-24 text-right tabular-nums'
  }
  if (moneyKeys.has(column.key)) return column.inlineFields?.length ? 'w-44 min-w-40 text-right tabular-nums' : 'w-32 min-w-28 text-right tabular-nums'
  if (column.key === 'containerRequirement' || column.key === 'containerRequirementId' || column.key === 'containerType' || column.key === 'feeType') return 'w-36 min-w-28'
  if (column.key === 'sealNo' || column.key === 'status') return 'w-28 min-w-24'
  if (column.key === 'placeRole') return 'w-44 min-w-40'
  if (column.key === 'place' || column.key === 'notes') return 'min-w-40'
  if (column.key === 'plannedActual') return 'w-40 min-w-36'
  return 'min-w-28'
}

function displayValue(column: ModuleLineColumn, value: unknown, row?: Record<string, unknown>) {
  if (isFileTable.value && row) {
    if (column.key === 'fileName') return fileTableRowName(row) || '—'
    if (column.key === 'uploadedBy') return fileTableRowBy(row) || '—'
    if (column.key === 'uploadedAt') {
      const created = fileTableRowCreated(row)
      return created ? formatDateTime(created) : '—'
    }
  }
  if (value === undefined || value === null || value === '') return '—'
  if (column.type === 'number') {
    const number = Number(value)
    if (!Number.isFinite(number)) return String(value)
    if (moneyKeys.has(column.key)) {
      const currency = row?.currency ? String(row.currency) : undefined
      if (column.key === 'total' && currency) return formatMoney(number, currency)
      return formatMoney(number, currency)
    }
    return formatNumber(number, { maximumFractionDigits: 2, minimumFractionDigits: 0 })
  }
  if (column.type === 'date') return formatDate(value)
  if (column.type === 'datetime') return formatDateTime(value)
  return String(value)
}

function lineDateGranularity(column: ModuleLineColumn): DatePickerGranularity | null {
  if (column.type === 'datetime') return 'minute'
  if (column.type === 'date') return 'day'
  if (/At$|Time$/i.test(column.key)) return 'minute'
  if (/Date$/i.test(column.key)) return 'day'
  return null
}

function columnHeader(column: ModuleLineColumn) {
  return h('div', { class: numericKeys.has(column.key) ? 'text-right' : '' }, [
    h('span', fieldLabel(column)),
    column.required
      ? h('span', { class: 'ms-0.5 text-error', 'aria-hidden': 'true' }, '*')
      : null,
  ])
}

function inlineNumberFieldsCell(column: ModuleLineColumn, row: Record<string, unknown>, index: number) {
  const inlineFields = column.inlineFields || []
  const formatInlineNumber = (value: unknown) =>
    formatNumber(value, { maximumFractionDigits: 2, minimumFractionDigits: 0 })
  const summary = inlineFields
    .map(field => formatInlineNumber(row[field.key]))
    .join(' / ')
  const main = h('span', {
    class: [columnCellClass(column), 'block truncate tabular-nums text-xs'],
    title: summary,
  }, summary || '—')
  if (!inlineFields.length) return main
  if (props.disabled) return main
  return h('div', { class: 'space-y-0.5 text-right' }, [
    inlineFields.map(field =>
      h('div', { class: 'flex items-center justify-end gap-1' }, [
        h('span', { class: 'text-[11px] leading-none text-muted' }, fieldLabel(field)),
        h(TableInputNumber, {
          'modelValue': Number(row[field.key] || 0),
          'increment': false,
          'decrement': false,
          'size': cellSize.value,
          'class': 'w-20',
          'ui': { base: 'text-right tabular-nums' },
          'aria-label': fieldLabel(field),
          'onUpdate:modelValue': (value: number | null) => updateCell(index, field.key, value ?? 0),
        }),
      ]),
    ),
  ])
}

function inlineMoneyCell(column: ModuleLineColumn, row: Record<string, unknown>, index: number) {
  const inlineFields = column.inlineFields || []
  const main = h('span', {
    class: [columnCellClass(column), 'block truncate text-xs'],
    title: String(row[column.key] ?? ''),
  }, displayValue(column, row[column.key], row))
  if (!inlineFields.length) return main
  const formatInlineMoney = (value: unknown) => formatMoney(value)
  if (props.disabled) {
    const parts = inlineFields
      .map(field => ({ label: fieldLabel(field), value: Number(row[field.key] ?? 0) }))
      .filter(part => Number.isFinite(part.value) && part.value !== 0)
    if (!parts.length) return main
    return h('div', { class: 'space-y-0.5' }, [
      main,
      h('div', { class: 'space-y-0.5 text-right text-[11px] leading-tight text-muted tabular-nums' }, parts.map(part =>
        h('div', { title: `${part.label} ${formatInlineMoney(part.value)}` }, `${part.label} ${formatInlineMoney(part.value)}`),
      )),
    ])
  }
  return h('div', { class: 'space-y-0.5 text-right' }, [
    main,
    h('div', { class: 'space-y-0.5' }, inlineFields.map(field =>
      h('div', { class: 'flex items-center justify-end gap-1' }, [
        h('span', { class: 'text-[11px] leading-none text-muted' }, fieldLabel(field)),
        h(TableInputNumber, {
          'modelValue': Number(row[field.key] || 0),
          'increment': false,
          'decrement': false,
          'size': cellSize.value,
          'class': 'w-20',
          'ui': { base: 'text-right tabular-nums' },
          'aria-label': fieldLabel(field),
          'onUpdate:modelValue': (value: number | null) => updateCell(index, field.key, value ?? 0),
        }),
      ]),
    )),
  ])
}

const rows = computed({
  get: () => props.modelValue || [],
  set: value => emit('update:modelValue', value),
})

const tableRows = computed(() => rows.value.map((row, index) => ({ ...row, _rowIndex: index })))

function updateCell(index: number, key: string, value: unknown) {
  const next = rows.value.map((row, i) => i === index ? { ...row, [key]: value } : row)
  if (props.table.key === 'otherCharges') {
    const row = next[index]
    if (!row) return
    const qty = Number(row.quantity || 0)
    const selling = Number(row.sellingRate || 0)
    next[index] = { ...row, amount: qty * selling }
  }
  if (props.table.key === 'feeLines') {
    const row = next[index]
    if (!row) return
    const amount = Math.max(0, Number(row.quantity || 0) * Number(row.unitAmount || 0) - Number(row.discount || 0))
    next[index] = { ...row, amount: amount + Number(row.taxAmount || 0) }
  }
  if (props.table.key === 'pricingLines') {
    const row = next[index]
    if (!row) return
    const subtotal = Number(row.quantity || 0) * Number(row.unitPrice || 0)
    const discount = Number(row.discountAmount || 0)
    const taxable = Math.max(0, subtotal - discount)
    const tax = Number(row.taxAmount || 0)
    next[index] = { ...row, lineTotal: Number((taxable + tax).toFixed(2)) }
  }
  if (props.table.key === 'lines') {
    const row = next[index]
    if (!row) return
    const taxable = Math.max(0, Number(row.quantity || 0) * Number(row.unitAmount || 0) - Number(row.discount || 0))
    const tax = Number(row.taxAmount || row.tax || 0)
    next[index] = { ...row, amount: Number((taxable + tax).toFixed(2)) }
  }

  rows.value = next
}

function addRow() {
  if (isFileTable.value) {
    openPicker()
    return
  }
  const blank = Object.fromEntries(props.table.columns.map((column) => {
    if (column.type === 'number') return [column.key, 0]
    if (column.type === 'checkbox') return [column.key, String(column.options?.[1] ?? 'No')]
    if (column.type === 'select') return [column.key, column.optionItems?.[0]?.value || column.options?.[0] || '']
    return [column.key, '']
  }))
  for (const column of props.table.columns) {
    for (const inline of column.inlineFields || []) {
      if (!(inline.key in blank)) blank[inline.key] = 0
    }
  }
  if (props.table.key === 'containerRequirements') {
    blank.quantity = 1
    blank.actualQuantity = 0
    blank.remaining = 1
  }
  if (props.table.key === 'actualContainers') {
    blank.status = 'Expected'
    blank.netWeightKg = 0
    blank.grossWeightKg = 0
    blank.containerNo = ''
  }
  if (props.table.key === 'places') {
    blank.placeRole = 'Pickup'
    blank.place = ''
    blank.plannedActual = ''
    blank.notes = ''
    blank.sequence = rows.value.length + 1
  }
  rows.value = [...rows.value, blank]
}

function onFilesChosen(event: Event) {
  const added = rowsFromInput(event)
  if (added.length) rows.value = [...rows.value, ...added]
}

function fileNameCell(row: Record<string, unknown>) {
  const name = fileTableRowName(row) || '—'
  const icon = fileTypeIcon({ name, mimeType: String(row.mimeType || '') })
  const href = name === '—' ? null : filePreviewHref(row)
  const labelClass = props.compact
    ? 'block min-w-0 truncate text-xs font-medium text-highlighted'
    : 'block min-w-0 truncate text-sm font-medium text-highlighted'
  const label = href
    ? h('a', {
      href,
      target: '_blank',
      rel: 'noopener noreferrer',
      class: [labelClass, 'hover:text-primary hover:underline'],
      title: name,
      'aria-label': t('app.ui.previewFile', { name }),
    }, name)
    : h('span', { class: labelClass, title: name }, name)
  return h('div', { class: 'flex min-w-0 items-center gap-1.5' }, [
    h(TableIcon, { name: icon.icon, class: ['size-4 shrink-0', icon.class] }),
    label,
  ])
}

function removeRow(index: number) {
  const row = rows.value[index]
  if (row) revokeFilePreview(row)
  rows.value = rows.value.filter((_, i) => i !== index)
}

const columns = computed<TableColumn<Record<string, unknown>>[]>(() => {
  const cols: TableColumn<Record<string, unknown>>[] = [
    {
      id: 'rowNumber',
      header: '#',
      cell: ({ row }) => h('span', { class: props.compact ? 'text-[11px] tabular-nums text-muted' : 'text-xs tabular-nums text-muted' }, Number(row.original._rowIndex || 0) + 1),
      enableSorting: false,
    },
    ...props.table.columns.map(column => ({
      accessorKey: column.key,
      header: () => columnHeader(column),
      enableSorting: false,
      cell: ({ row }: { row: { original: Record<string, unknown> } }) => {
        const index = Number(row.original._rowIndex || 0)
        if (isFileTable.value && column.key === 'fileName') return fileNameCell(row.original)
        if (column.inlineFields?.length && !moneyKeys.has(column.key)) {
          return inlineNumberFieldsCell(column, row.original, index)
        }
        if (props.disabled || column.computed || isFileTable.value) {
          return inlineMoneyCell(column, row.original, index)
        }
        if (column.type === 'checkbox') {
          return h(TableCheckbox, {
            'modelValue': row.original[column.key],
            'trueValue': String(column.options?.[0] ?? 'Yes'),
            'falseValue': String(column.options?.[1] ?? 'No'),
            'disabled': props.disabled || column.computed,
            'size': cellSize.value,
            'aria-label': fieldLabel(column),
            'onUpdate:modelValue': (value: unknown) => updateCell(index, column.key, value),
          })
        }
        if (column.type === 'select') {
          const items = column.optionItems?.length
            ? column.optionItems
            : (column.options || []).filter(Boolean).map(option => ({ label: option, value: option }))
          return h(TableSelect, {
            'modelValue': String(row.original[column.key] || '') || undefined,
            'items': items,
            'disabled': props.disabled || column.computed,
            'size': cellSize.value,
            'class': ['w-full', columnCellClass(column)],
            'onUpdate:modelValue': (value: unknown) => updateCell(index, column.key, value),
          })
        }
        if (column.type === 'number') {
          return h(TableInputNumber, {
            'modelValue': Number(row.original[column.key] || 0),
            'disabled': props.disabled || column.computed,
            'increment': false,
            'decrement': false,
            'size': cellSize.value,
            'class': ['w-full', columnCellClass(column)],
            'ui': { base: 'text-right tabular-nums' },
            'onUpdate:modelValue': (value: number | null) => updateCell(index, column.key, value ?? 0),
          })
        }
        const dateGranularity = lineDateGranularity(column)
        if (dateGranularity) {
          return h(TableDate, {
            'modelValue': String(row.original[column.key] ?? ''),
            'granularity': dateGranularity,
            'disabled': props.disabled || column.computed,
            'size': cellSize.value,
            'class': `w-full ${columnCellClass(column)}`,
            'onUpdate:modelValue': (value: string) => updateCell(index, column.key, value),
          })
        }
        return h(TableInput, {
          'modelValue': String(row.original[column.key] ?? ''),
          'disabled': props.disabled || column.computed,
          'size': cellSize.value,
          'class': `w-full ${columnCellClass(column)}`,
          'onUpdate:modelValue': (value: string) => updateCell(index, column.key, value),
        })
      },
    })),
  ]
  if (!props.disabled) {
    cols.push({
      id: 'actions',
      header: () => h('span', { class: 'sr-only' }, t('common.actions')),
      enableSorting: false,
      cell: ({ row }) => {
        const items: Array<Array<{ label: string, icon: string, color?: 'error', onSelect: () => void }>> = [[]]
        const actions = items[0]!
        if (isFileTable.value && filePreviewHref(row.original)) {
          actions.push({
            label: t('app.ui.preview'),
            icon: 'i-lucide-external-link',
            onSelect: () => {
              const href = filePreviewHref(row.original)
              if (href && import.meta.client) window.open(href, '_blank', 'noopener,noreferrer')
            },
          })
        }
        actions.push({
          label: t('actions.delete'),
          icon: 'i-lucide-trash-2',
          color: 'error',
          onSelect: () => removeRow(Number(row.original._rowIndex || 0)),
        })
        return h(TableMenu, {
          items,
        }, {
          default: () => h(TableButton, {
            icon: 'i-lucide-ellipsis',
            color: 'neutral',
            variant: 'ghost',
            size: 'xs',
            square: true,
            'aria-label': t('common.actions'),
          }),
        })
      },
    })
  }
  else if (props.viewOnlyActions) {
    cols.push({
      id: 'actions',
      header: () => h('span', { class: 'sr-only' }, t('common.actions')),
      enableSorting: false,
      cell: ({ row }) => h(TableButton, {
        label: 'View',
        color: 'neutral',
        variant: 'ghost',
        size: 'xs',
        onClick: () => emit('rowAction', 'view', row.original),
      }),
    })
  }
  return cols
})
</script>

<template>
  <section :class="compact ? 'space-y-2' : 'space-y-3'">
    <div class="flex items-center justify-between gap-2">
      <h3 :class="compact ? 'text-xs font-medium text-highlighted' : 'text-sm font-medium text-highlighted'">
        {{ tableTitle(table) }}
      </h3>
      <UButton
v-if="!disabled"
:size="compact ? 'xs' : 'sm'"
color="neutral"
variant="soft"
        :icon="isFileTable ? 'i-lucide-upload' : 'i-lucide-plus'"
        :label="table.addLabelKey && te(table.addLabelKey) ? t(table.addLabelKey) : (table.addLabel || t('app.ui.addRow'))"
        @click="addRow" />
    </div>
    <input
v-if="isFileTable && !disabled"
:ref="setFileInput"
type="file"
multiple
class="hidden"
@change="onFilesChosen">
    <div class="overflow-x-auto">
      <UTable
:data="tableRows"
:columns="columns"
        :get-row-id="(row: Record<string, unknown>) => String(row._rowIndex ?? '')"
        :class="['app-table min-w-max', compact ? 'app-table-compact' : '']"
:ui="tableUi" />
    </div>
  </section>
</template>

