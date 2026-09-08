/** Shared bounded table page-size helpers for server-backed data. */

export const TABLE_PAGE_SIZES = [10, 20, 50, 100, 200] as const

/**
 * Parse `route.query.limit` or a select value into a page size.
 * Accepts `all` / `-1` for show-all; otherwise 10 | 20 | 50 | 100 | 200.
 */
export function parsePageLimit(raw: unknown, defaultLimit = 10): number {
  if (raw === 'all' || raw === '-1') return defaultLimit
  if (typeof raw === 'number' && raw === -1) return defaultLimit

  const n = Number(raw)
  if (!Number.isFinite(n) || n <= 0) return defaultLimit
  if ((TABLE_PAGE_SIZES as readonly number[]).includes(n)) return n
  if (n > 200) return 200
  return Math.min(Math.max(Math.round(n), 10), 100)
}

/** Serialize for URL query — omit when equal to default. */
export function serializePageLimit(limit: number, defaultLimit = 10): string | undefined {
  if (limit === defaultLimit) return undefined
  return String(limit)
}

/** Items-per-page for UPagination when showing all (single page). */
export function paginationItemsPerPage(limit: number): number {
  return Math.max(limit, 1)
}
