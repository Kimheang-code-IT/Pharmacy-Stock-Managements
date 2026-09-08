import type { PersonSummary, AttachmentMeta } from '~/types/stock-pos/common'
import { createId, nowIso } from './query'

export const people: PersonSummary[] = [
  { id: 'p1', name: 'Sokha Chan', email: 'sokha@stockpos.local' },
  { id: 'p2', name: 'Dara Kim', email: 'dara@stockpos.local' },
  { id: 'p3', name: 'Sreymom Lim', email: 'sreymom@stockpos.local' },
  { id: 'p4', name: 'Vannak Ouk', email: 'vannak@stockpos.local' },
  { id: 'p5', name: 'Chenda Meas', email: 'chenda@stockpos.local' },
]

export function person(i = 0) {
  return people[i % people.length]!
}

export function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString()
}

export function dateOnly(n: number) {
  return daysAgo(n).slice(0, 10)
}

export function seedAttachments(count = 2): AttachmentMeta[] {
  return Array.from({ length: count }, (_, i) => ({
    id: createId('att'),
    name: i === 0 ? 'product-spec.pdf' : 'delivery-note.zip',
    mimeType: i === 0 ? 'application/pdf' : 'application/zip',
    sizeBytes: 120_000 + i * 80_000,
    uploadedBy: person(i),
    uploadedAt: daysAgo(i),
    storageSource: 'local',
  }))
}

export { nowIso, createId }

/* ------------------------------------------------------------------ */
/* Stock & POS seed catalogue                                          */
/* ------------------------------------------------------------------ */

export const seedUsers = [
  {
    id: 'u1', username: 'admin', displayName: 'Sokha Chan', email: 'admin@stockpos.local',
    roleId: '1', status: 'Active', lastLogin: daysAgo(0),
    permissions: ['ALL_PAGES'], effectivePermissions: ['ALL_PAGES'],
  },
  {
    id: 'u2', username: 'dara', displayName: 'Dara Kim', email: 'dara@stockpos.local',
    roleId: '2', status: 'Active', lastLogin: daysAgo(1),
    permissions: ['dashboard.view', 'categories.view', 'brand.view', 'products.view', 'customers.view', 'suppliers.view', 'pos.view', 'reports.view', 'sales.view', 'delivery.view'],
    effectivePermissions: ['dashboard.view', 'categories.view', 'brand.view', 'products.view', 'customers.view', 'suppliers.view', 'pos.view', 'reports.view', 'sales.view', 'delivery.view'],
  },
  {
    id: 'u3', username: 'sreymom', displayName: 'Sreymom Lim', email: 'sreymom@stockpos.local',
    roleId: '3', status: 'Inactive', lastLogin: daysAgo(12),
    permissions: ['dashboard.view', 'reports.view'],
    effectivePermissions: ['dashboard.view', 'reports.view'],
  },
]

export const seedRoles = [
  {
    id: '1', name: 'Administrator', description: 'Full access to every page and action.',
    permissions: ['ALL_PAGES'], userCount: 1, permissionCount: 0, status: 'Active',
  },
  {
    id: '2', name: 'Store Staff', description: 'POS, stock and customer operations.',
    permissions: [
      'dashboard.view', 'categories.view', 'brand.view', 'products.view', 'products.edit', 'products.create',
      'customers.view', 'customers.create', 'customers.edit', 'suppliers.view',
      'pos.view', 'pos.create', 'sales.view', 'sales.create', 'reports.view',
      'delivery.view', 'delivery.create', 'delivery.update', 'delivery.confirm', 'delivery.deliver', 'delivery.cancel',
    ],
    userCount: 1, permissionCount: 22, status: 'Active',
  },
  {
    id: '3', name: 'Report Viewer', description: 'Read-only dashboard and reports.',
    permissions: ['dashboard.view', 'reports.view', 'sales.view', 'products.view'],
    userCount: 1, permissionCount: 4, status: 'Active',
  },
]

export const seedDocumentSequences = [
  { id: 'ds1', documentType: 'SALE', prefix: 'SALE', paddingLength: 5, year: null, lastValue: 1042, status: 'ACTIVE' },
  { id: 'ds2', documentType: 'STOCK_IN', prefix: 'PIN', paddingLength: 5, year: null, lastValue: 87, status: 'ACTIVE' },
  { id: 'ds3', documentType: 'CUSTOMER', prefix: 'CUS', paddingLength: 4, year: null, lastValue: 63, status: 'ACTIVE' },
  { id: 'ds4', documentType: 'SUPPLIER', prefix: 'SUP', paddingLength: 4, year: null, lastValue: 21, status: 'ACTIVE' },
  { id: 'ds5', documentType: 'PAYMENT', prefix: 'PAY', paddingLength: 5, year: null, lastValue: 311, status: 'ACTIVE' },
  { id: 'ds6', documentType: 'ADJUSTMENT', prefix: 'ADJ', paddingLength: 5, year: null, lastValue: 15, status: 'ACTIVE' },
  { id: 'ds7', documentType: 'DELIVERY_NOTE', prefix: 'DN', paddingLength: 6, year: null, lastValue: 7, status: 'ACTIVE' },
  { id: 'ds8', documentType: 'SALE_RETURN', prefix: 'SRT', paddingLength: 6, year: null, lastValue: 0, status: 'ACTIVE' },
  { id: 'ds9', documentType: 'PURCHASE_RETURN', prefix: 'PRT', paddingLength: 6, year: null, lastValue: 0, status: 'ACTIVE' },
]

export const seedAuditLogs = [
  { id: 'al1', occurredAt: daysAgo(0), userName: 'Sokha Chan', user: 'Sokha Chan', eventType: 'SALE', action: 'create', entityType: 'Sale', entityId: 'SALE-01042', entityLabel: 'SALE-01042', entity: 'SALE-01042', result: 'SUCCESS', ipAddress: '10.0.0.14', ipDevice: '10.0.0.14' },
  { id: 'al2', occurredAt: daysAgo(0), userName: 'Dara Kim', user: 'Dara Kim', eventType: 'STOCK', action: 'stock_in', entityType: 'Product', entityId: 'PRD-0007', entityLabel: 'PRD-0007', entity: 'PRD-0007', result: 'SUCCESS', ipAddress: '10.0.0.22', ipDevice: '10.0.0.22' },
  { id: 'al3', occurredAt: daysAgo(1), userName: 'Dara Kim', user: 'Dara Kim', eventType: 'DEBT', action: 'payment', entityType: 'Customer', entityId: 'CUS-0012', entityLabel: 'Nita Sok', entity: 'CUS-0012', result: 'SUCCESS', ipAddress: '10.0.0.22', ipDevice: '10.0.0.22' },
  { id: 'al4', occurredAt: daysAgo(2), userName: 'Sokha Chan', user: 'Sokha Chan', eventType: 'AUTH', action: 'login', entityType: 'User', entityId: 'u1', entityLabel: 'admin', entity: 'admin', result: 'SUCCESS', ipAddress: '10.0.0.14', ipDevice: '10.0.0.14' },
  { id: 'al5', occurredAt: daysAgo(3), userName: 'Unknown', user: 'Unknown', eventType: 'AUTH', action: 'login', entityType: 'User', entityId: 'u2', entityLabel: 'dara', entity: 'dara', result: 'FAILED', ipAddress: '192.168.4.7', ipDevice: '192.168.4.7' },
  { id: 'al6', occurredAt: daysAgo(4), userName: 'Sokha Chan', user: 'Sokha Chan', eventType: 'ADMIN', action: 'update', entityType: 'User', entityId: 'u3', entityLabel: 'sreymom', entity: 'sreymom', result: 'SUCCESS', ipAddress: '10.0.0.14', ipDevice: '10.0.0.14' },
]