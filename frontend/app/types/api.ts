import type { ColumnFiltersState } from '@tanstack/vue-table'

export interface TableQueryParams {
  q?: string
  page: number
  limit: number
  sort?: string
  filters?: ColumnFiltersState
  startDate?: string
  endDate?: string
}
