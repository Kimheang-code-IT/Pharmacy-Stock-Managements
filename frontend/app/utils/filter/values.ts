/** Normalize query/select values into a unique list of filter tokens. */
export function parseFilterQuery(value: unknown): string[] {
  if (value == null || value === '') return []
  if (Array.isArray(value)) {
    return [...new Set(value.flatMap(item => parseFilterQuery(item)))]
  }
  if (typeof value === 'object' && 'value' in value) {
    return parseFilterQuery((value as { value: unknown }).value)
  }
  return [...new Set(
    String(value)
      .split(',')
      .map(part => part.trim())
      .filter(Boolean),
  )]
}

/** True when the row should remain visible for this filter (empty = no restriction). */
export function matchesFilter(rowValue: unknown, selected: unknown): boolean {
  const values = parseFilterQuery(selected)
  if (!values.length) return true
  return values.includes(String(rowValue ?? ''))
}

const FILTER_MAX_WITH_DATE = 3
const FILTER_MAX_WITHOUT_DATE = 4

/**
 * Cap toolbar filter selects: 3 when a date range sits beside them, 4 otherwise.
 * A 4-select toolbar never shows status; when trimming an over-limit list,
 * status filters are dropped first.
 */
export function limitFilterSelects<T>(
  filters: T[],
  hasDatePicker: boolean,
  isStatus: (item: T) => boolean = () => false,
): T[] {
  const max = hasDatePicker ? FILTER_MAX_WITH_DATE : FILTER_MAX_WITHOUT_DATE
  if (filters.length <= max) {
    const dropStatus = max === FILTER_MAX_WITHOUT_DATE
      && filters.length === max
      && filters.some(isStatus)
    return dropStatus ? filters.filter(item => !isStatus(item)) : filters
  }
  const pool = filters.filter(item => !isStatus(item))
  return (pool.length >= max ? pool : filters).slice(0, max)
}
