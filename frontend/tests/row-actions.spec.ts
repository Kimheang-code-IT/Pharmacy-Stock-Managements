import { describe, expect, it } from 'vitest'
import {
  HARD_DELETE_COLLECTIONS,
  STATUS_TOGGLE_COLLECTIONS,
  canHardDeleteRecord,
  isRecordInactive,
  statusValueFor,
  supportsHardDelete,
  supportsStatusToggle,
} from '../app/utils/module/row-actions'

describe('row action collection rules', () => {
  it('exposes hard delete only for dependency-checked collections', () => {
    for (const collection of ['categories', 'uoms', 'products', 'suppliers', 'customers', 'roles', 'documentSequences']) {
      expect(supportsHardDelete(collection), collection).toBe(true)
    }
    for (const collection of ['users', 'deliveryNotes', 'sales', 'stockIns', 'customerDebts', 'supplierDebts', 'auditLogs']) {
      expect(supportsHardDelete(collection), collection).toBe(false)
    }
  })

  it('exposes a status toggle only for ACTIVE/INACTIVE-style collections', () => {
    for (const collection of ['categories', 'uoms', 'products', 'suppliers', 'customers', 'users', 'roles', 'documentSequences']) {
      expect(supportsStatusToggle(collection), collection).toBe(true)
    }
    for (const collection of ['deliveryNotes', 'sales', 'stockIns', 'customerDebts', 'auditLogs']) {
      expect(supportsStatusToggle(collection), collection).toBe(false)
    }
    expect(supportsHardDelete(undefined)).toBe(false)
    expect(supportsStatusToggle(null)).toBe(false)
  })

  it('treats every inactive dialect as inactive', () => {
    for (const status of ['Inactive', 'INACTIVE', 'inactive', 'Disabled', 'DISABLED', 'Deactivated']) {
      expect(isRecordInactive(status), status).toBe(true)
    }
    for (const status of ['Active', 'ACTIVE', 'Low Stock', '', null, undefined]) {
      expect(isRecordInactive(status), String(status)).toBe(false)
    }
  })

  it('allows hard delete only for inactive rows on status-bearing tables', () => {
    expect(canHardDeleteRecord('categories', 'ACTIVE')).toBe(false)
    expect(canHardDeleteRecord('categories', 'INACTIVE')).toBe(true)
    expect(canHardDeleteRecord('roles', 'ACTIVE')).toBe(false)
    expect(canHardDeleteRecord('roles', 'DISABLED')).toBe(true)
    expect(canHardDeleteRecord('users', 'Inactive')).toBe(false)
    expect(canHardDeleteRecord('sales', 'ACTIVE')).toBe(false)
  })

  it('maps the active toggle to the backend status dialect per collection', () => {
    expect(statusValueFor('users', true)).toBe('Active')
    expect(statusValueFor('users', false)).toBe('Inactive')
    expect(statusValueFor('roles', true)).toBe('ACTIVE')
    expect(statusValueFor('roles', false)).toBe('DISABLED')
    expect(statusValueFor('categories', true)).toBe('ACTIVE')
    expect(statusValueFor('categories', false)).toBe('INACTIVE')
    expect(statusValueFor('products', false)).toBe('INACTIVE')
  })

  it('keeps the hard-delete and status sets aligned with the action model', () => {
    for (const collection of HARD_DELETE_COLLECTIONS) {
      expect(STATUS_TOGGLE_COLLECTIONS.has(collection), collection).toBe(true)
    }
  })
})
