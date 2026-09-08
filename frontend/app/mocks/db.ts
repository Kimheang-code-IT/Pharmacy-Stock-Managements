import type { AppRecord } from '~/config/admin-seed'
import { createId, nowIso } from './query'
import {
  brands,
  categories,
  customerDebtPayments,
  customerDebts,
  customers,
  deliveryNotes,
  expenses,
  productSalePrices,
  products,
  sales,
  stockIns,
  stockMovements,
  supplierDebtPayments,
  supplierDebts,
  suppliers,
  uoms,
} from './stock-seed'
import {
  seedAuditLogs,
  seedDocumentSequences,
  seedRoles,
  seedUsers,
} from './seed'

export interface MockCollections {
  categories: AppRecord[]
  uoms: AppRecord[]
  brands: AppRecord[]
  products: AppRecord[]
  productSalePrices: AppRecord[]
  suppliers: AppRecord[]
  customers: AppRecord[]
  sales: AppRecord[]
  deliveryNotes: AppRecord[]
  stockIns: AppRecord[]
  stockMovements: AppRecord[]
  customerDebtPayments: AppRecord[]
  customerDebts: AppRecord[]
  supplierDebtPayments: AppRecord[]
  supplierDebts: AppRecord[]
  expenses: AppRecord[]
  users: AppRecord[]
  roles: AppRecord[]
  documentSequences: AppRecord[]
  auditLogs: AppRecord[]
}

export interface MockDb {
  collections: MockCollections
}

let db: MockDb | null = null

/** Lazily-created client-session mock database (seed cloned once). */
export function useMockDb(): MockDb {
  if (!db) {
    db = {
      collections: {
        categories: structuredClone(categories),
        uoms: structuredClone(uoms),
        brands: structuredClone(brands),
        products: structuredClone(products),
        productSalePrices: structuredClone(productSalePrices),
        suppliers: structuredClone(suppliers),
        customers: structuredClone(customers),
        sales: structuredClone(sales),
        deliveryNotes: structuredClone(deliveryNotes),
        stockIns: structuredClone(stockIns),
        stockMovements: structuredClone(stockMovements),
        customerDebtPayments: structuredClone(customerDebtPayments),
        customerDebts: structuredClone(customerDebts),
        supplierDebtPayments: structuredClone(supplierDebtPayments),
        supplierDebts: structuredClone(supplierDebts),
        expenses: structuredClone(expenses),
        users: structuredClone(seedUsers),
        roles: structuredClone(seedRoles),
        documentSequences: structuredClone(seedDocumentSequences),
        auditLogs: structuredClone(seedAuditLogs),
      },
    }
  }
  return db
}

export function mockRecords(collection: string): AppRecord[] {
  const collections: MockCollections = useMockDb().collections
  return (collections as unknown as Record<string, AppRecord[]>)[collection] || []
}

export function mockInsert(collection: string, input: Record<string, unknown>): AppRecord {
  const rows = mockRecords(collection)
  const record: AppRecord = {
    ...structuredClone(input),
    id: createId('m'),
    createdAt: String(input.createdAt || nowIso()),
  } as AppRecord
  rows.unshift(record)
  return record
}

export function mockUpdate(collection: string, id: string, input: Record<string, unknown>): AppRecord | null {
  const rows = mockRecords(collection)
  const index = rows.findIndex(row => String(row.id) === String(id))
  if (index < 0) return null
  const updated = { ...rows[index]!, ...structuredClone(input), id: String(id) } as AppRecord
  rows[index] = updated
  return updated
}

export function mockRemove(collection: string, id: string): void {
  const rows = mockRecords(collection)
  const index = rows.findIndex(row => String(row.id) === String(id))
  if (index >= 0) rows.splice(index, 1)
}
