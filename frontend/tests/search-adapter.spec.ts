import { describe, expect, it } from 'vitest'
import { adaptBackendSearchHits } from '../app/composables/search/useSearch'

describe('backend search response adapter', () => {
  it('maps the { hits, total } backend contract to UI search hits', () => {
    const hits = adaptBackendSearchHits([
      { id: 'sale-001', type: 'sale', title: 'INV-2026-000001', subtitle: 'Walk-in', url: '/reports/sales' },
      { id: 'prd-001', type: 'product', title: 'Widget A', subtitle: 'P-001', url: '/stock/prd-001' },
      { id: '1', type: 'user', title: 'Admin', subtitle: 'admin@gmail.com', url: '/administration/users/1' },
    ])

    expect(hits).toHaveLength(3)
    expect(hits[0]).toMatchObject({
      id: 'sale-001',
      entityType: 'document',
      entityId: 'sale-001',
      title: 'INV-2026-000001',
      snippet: 'Walk-in',
      url: '/reports/sales',
    })
    expect(hits[0]?.sourceLabel).toBe('Sales')
    expect(hits[1]?.sourceLabel).toBe('Stock')
    expect(hits[2]?.entityType).toBe('user')
    expect(hits.every(hit => typeof hit.score === 'number')).toBe(true)
  })

  it('maps an empty hit list to an empty array', () => {
    expect(adaptBackendSearchHits([])).toEqual([])
  })
})
