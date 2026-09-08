import type { AppRecord } from '~/config/admin-seed'

/** Stock & POS document types — one sequence row per type (configured in admin UI). */
export const DEFAULT_DOCUMENT_SEQUENCE_TYPES = [
  'SALE',
  'STOCK_IN',
  'ADJUSTMENT',
  'PAYMENT',
  'CUSTOMER',
  'SUPPLIER',
  'PRODUCT',
] as const

export const DOCUMENT_SEQUENCE_TYPES = DEFAULT_DOCUMENT_SEQUENCE_TYPES

export const DOCUMENT_SEQUENCE_STATUSES = ['ACTIVE', 'INACTIVE'] as const

const TYPE_LABELS: Record<string, string> = {
  SALE: 'Sale / Invoice',
  STOCK_IN: 'Stock In',
  ADJUSTMENT: 'Stock Adjustment',
  PAYMENT: 'Payment',
  CUSTOMER: 'Customer',
  SUPPLIER: 'Supplier',
  PRODUCT: 'Product',
}

const LEGACY_TYPES: Record<string, string> = {
  Quotation: 'QUOTATION',
  'Service Order': 'SERVICE_ORDER',
  'Service Charge': 'SERVICE_CHARGE',
  'Financial Document': 'CUSTOMER_INVOICE',
  Receipt: 'CUSTOMER_RECEIPT',
  Payment: 'PAYMENT',
  Journal: 'JOURNAL',
}

export function normalizeDocumentSequenceType(value: unknown) {
  const raw = String(value || '').trim().toUpperCase().replace(/\s+/g, '_')
  return LEGACY_TYPES[raw] || LEGACY_TYPES[String(value || '')] || raw
}

export function isDocumentSequenceType(value: string) {
  const normalized = normalizeDocumentSequenceType(value)
  return (DEFAULT_DOCUMENT_SEQUENCE_TYPES as readonly string[]).includes(normalized)
}

export function documentSequenceTypeLabel(value: unknown) {
  const type = normalizeDocumentSequenceType(value)
  return TYPE_LABELS[type] || type.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase())
}

export function documentSequenceTypeOptions(existing: AppRecord[] = []) {
  const fromData = existing
    .map(row => normalizeDocumentSequenceType(row.documentType))
    .filter(Boolean)
  const values = [...new Set([...DEFAULT_DOCUMENT_SEQUENCE_TYPES, ...fromData])]
  return values.map(value => ({
    label: documentSequenceTypeLabel(value),
    value,
  }))
}

export function documentSequencePreview(record: Record<string, unknown>) {
  const prefix = String(record.prefix || '').trim()
  const year = Number(record.year || record.periodYear || 0)
  const next = Math.max(0, Number(record.lastValue || 0)) + 1
  const padding = Math.max(1, Number(record.paddingLength || 6))
  const parts = [prefix, year > 0 ? year : null, String(next).padStart(padding, '0')].filter(Boolean)
  return parts.join('-')
}

export function normalizeDocumentSequenceRecord(record: AppRecord): AppRecord {
  const documentType = normalizeDocumentSequenceType(record.documentType)
  const year = Number(record.year || record.periodYear || 0)
  return {
    ...record,
    documentType,
    year: year > 0 ? year : null,
    prefix: String(record.prefix || '').trim(),
    lastValue: Math.max(0, Number(record.lastValue || 0)),
    paddingLength: Math.max(1, Number(record.paddingLength || 6)),
    status: String(record.status || 'ACTIVE').toUpperCase(),
  }
}
