import type { PaginationState } from '@tanstack/vue-table'
import { TABLE_VIRTUALIZE_AFTER } from '~/utils/table/theme'

type Translate = (key: string, values?: Record<string, unknown>) => string

/** Header counter: "6 of 6" for the row-action column. */
export function listTablePageSummary(
  t: Translate,
  total: number,
  pagination: Pick<PaginationState, 'pageIndex' | 'pageSize'>,
) {
  if (!total) return t('app.ui.ofZero')
  const start = pagination.pageIndex * pagination.pageSize
  const end = Math.min(start + pagination.pageSize, total)
  const shown = Math.max(0, end - start)
  return t('app.ui.of', { shown, total })
}

export function listTableSelectedIds(selection: Record<string, boolean>) {
  return Object.keys(selection).filter(id => selection[id])
}

export function listTableVirtualize(total: number, pageSize: number) {
  if (total < TABLE_VIRTUALIZE_AFTER && pageSize < TABLE_VIRTUALIZE_AFTER) return false as const
  return {
    estimateSize: 48,
    overscan: 12,
  }
}
