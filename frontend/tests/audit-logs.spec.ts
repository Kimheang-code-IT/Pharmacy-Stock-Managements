import { describe, expect, it } from 'vitest'
import type { ModuleConfig } from '../app/config/modules'
import { normalizeAuditLog, resolveAuditEntityPath } from '../app/utils/module/audit-logs'

const moduleStub = (partial: Partial<ModuleConfig>): ModuleConfig => ({
  path: '/stock', title: 'Stock', titleKm: '', singular: 'Product', singularKm: '',
  description: '', descriptionKm: '', icon: '', group: 'master', permission: 'products.view',
  collection: 'products', titleField: 'name', columns: [], fields: [], canCreate: true,
  ...partial,
})

describe('audit log table logic', () => {
  it('normalizes legacy audit rows for the table', () => {
    expect(normalizeAuditLog({ id: 'log-1', action: 'Updated product', module: 'Stock', recordNo: 'PRD-1', ipAddress: '192.168.1.1' })).toMatchObject({
      eventType: 'UPDATED_PRODUCT', entityType: 'Stock', entity: 'PRD-1', result: 'SUCCESS', ipDevice: '192.168.1.1',
    })
  })

  it('links an entity to an existing accessible record', () => {
    const path = resolveAuditEntityPath(
      { id: 'log-1', entityType: 'Product', entity: 'Widget A' },
      [moduleStub({})],
      collection => collection === 'products' ? [{ id: 'prd-1', name: 'Widget A', code: 'P-001' }] : [],
      () => true,
    )
    expect(path).toBe('/stock/prd-1')
  })

  it('does not create broken or unauthorized links', () => {
    const module = moduleStub({})
    expect(resolveAuditEntityPath({ id: 'log-1', entity: 'MISSING' }, [module], () => [], () => true)).toBe('')
    expect(resolveAuditEntityPath({ id: 'log-2', entity: 'Widget A' }, [module], () => [{ id: 'prd-1', name: 'Widget A' }], () => false)).toBe('')
  })
})
