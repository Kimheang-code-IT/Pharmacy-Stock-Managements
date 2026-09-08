import type { ApiMeta, ApiResponse, ListQuery } from '~/types/stock-pos/common'
import { TABLE_PAGE_SIZES } from '~/utils/pagination'

function delay(ms = 40) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export function paginateMeta(total: number, page: number, limit: number): ApiMeta {
  const safeLimit = Math.max(1, limit)
  return {
    page,
    limit: safeLimit,
    total,
    totalPages: Math.max(1, Math.ceil(total / safeLimit)),
  }
}

export function ok<T>(data: T, meta?: ApiMeta): ApiResponse<T> {
  return { data, meta }
}

/**
 * Optional mock network delay. Normal mock CRUD resolves immediately so the
 * mock-only release does not flash or retain API-style pending states.
 */
export async function mockLatency<T>(value: T, ms = 0): Promise<T> {
  if (ms > 0) await delay(ms)
  return value
}

export function applyListQuery<T extends Record<string, unknown>>(
  items: T[],
  query: ListQuery = {},
  searchKeys: string[] = ['title', 'name', 'code', 'referenceNumber', 'fileName', 'location', 'message', 'summary'],
): ApiResponse<T[]> {
  const page = Number(query.page || 1)
  let limit = Number(query.limit || 10)
  if (!Number.isFinite(limit) || limit <= 0) limit = TABLE_PAGE_SIZES[1]
  limit = Math.min(limit, TABLE_PAGE_SIZES.at(-1) || 100)
  let filtered = [...items]

  const q = String(query.q || '').trim().toLowerCase()
  if (q) {
    filtered = filtered.filter(item =>
      searchKeys.some((key) => {
        const value = item[key]
        return typeof value === 'string' && value.toLowerCase().includes(q)
      }),
    )
  }

  if (query.stage) {
    const stages = String(query.stage).split(',').filter(Boolean)
    filtered = filtered.filter(item => stages.includes(String(item.stage || '')))
  }
  if (query.status) {
    const statuses = String(query.status).split(',').filter(Boolean)
    filtered = filtered.filter(item => statuses.includes(String(item.status || '')))
  }

  for (const [key, value] of Object.entries(query)) {
    if (['q', 'page', 'limit', 'sort', 'view', 'stage', 'status', 'startDate', 'endDate'].includes(key)) continue
    if (value === undefined || value === '' || value === null) continue
    filtered = filtered.filter((item) => {
      const current = item[key]
      if (value === '__empty__') return current == null || current === ''
      if (typeof current === 'boolean') return current === (value === true || value === 'true')
      if (current && typeof current === 'object' && 'id' in (current as object)) {
        return String((current as { id: string }).id) === String(value)
      }
      return String(current ?? '') === String(value)
    })
  }

  if (query.startDate || query.endDate) {
    filtered = filtered.filter((item) => {
      const dateValue = String(
        item.receivedDate
        || item.sentDate
        || item.meetingDate
        || item.occurredAt
        || item.updatedAt
        || item.createdAt
        || '',
      )
      if (!dateValue) return true
      if (query.startDate && dateValue < String(query.startDate)) return false
      if (query.endDate && dateValue > String(query.endDate)) return false
      return true
    })
  }

  if (query.sort) {
    const desc = query.sort.startsWith('-')
    const key = desc ? query.sort.slice(1) : query.sort
    filtered.sort((a, b) => {
      const av = String(a[key] ?? '')
      const bv = String(b[key] ?? '')
      return desc ? bv.localeCompare(av) : av.localeCompare(bv)
    })
  }

  const total = filtered.length
  const start = (page - 1) * limit
  const data = filtered.slice(start, start + limit)
  return ok(data, paginateMeta(total, page, limit))
}

export function createId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`
}

export function nowIso() {
  return new Date().toISOString()
}
