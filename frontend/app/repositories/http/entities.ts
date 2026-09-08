import type { AppRecord } from '~/config/admin-seed'
import type { ApiMeta, ApiResponse } from '~/types/stock-pos/common'
import type { AppRolePermissionRow } from '~/types/stock-pos/entities'
import type {
  DashboardSummary,
  EntityListQuery,
  EntityListResult,
  EntityRepository,
  FinanceEntry,
  FinanceRepository,
  FinanceSummary,
  PosCommandRepository,
  PosCompleteSaleInput,
  ProductCostHistoryRow,
  ProductHistoryRow,
  ProductSalePriceRow,
  SaleReceipt,
  SearchRepository,
  SearchHitItem,
  StockHistoryKind,
  StockQueryRepository,
} from '~/repositories/contracts/entities'
import { ApiEndpoints, CollectionEndpoints, type ApiCollection } from '~/utils/constants/api-endpoints'
import { documentSequencePreview } from '~/utils/document-sequences'
import { ROLE_DOCUMENT_TYPES, normalizePermissionRows } from '~/utils/role/permissions'

export function metaOf(response: unknown): ApiMeta | null {
  const meta = (response as ApiResponse<unknown>)?.meta
  return meta ? { ...meta } : null
}

export function unwrap<T>(response: unknown): T {
  if (response && typeof response === 'object' && 'data' in (response as object)) {
    return (response as ApiResponse<T>).data
  }
  return response as T
}

/** Fields the UI keeps locally but the backend does not accept on writes. */
const UI_ONLY_FIELDS = new Set([
  'nextNumberPreview',
  'resetRule',
  'userCount',
  'permissionCount',
  'permissionRows',
  'telegramUsername',
  'telegramChatId',
  'lastLogin',
  'telegramLinked',
])

function stripUiOnlyFields(input: Record<string, unknown>): Record<string, unknown> {
  const output: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input)) {
    if (!UI_ONLY_FIELDS.has(key)) output[key] = value
  }
  return output
}

/** Flat backend permission keys â†’ UI permission-matrix rows. */
let ROLE_DOCUMENT_TYPES_CACHE: Array<{ value: string, permissionPrefix: string, actions: readonly string[] }> = []

/** Injected once by the repository selector to avoid import cycles. */
export function configureRoleMatrix(
  definitions: Array<{ value: string, permissionPrefix: string, actions: readonly string[] }>,
) {
  ROLE_DOCUMENT_TYPES_CACHE = definitions
}

function permissionRowsFromFlatKeys(keys: string[] | null | undefined): AppRolePermissionRow[] {
  if (keys?.includes('ALL_PAGES')) {
    return normalizePermissionRows(ROLE_DOCUMENT_TYPES_CACHE.map(definition => ({
      id: `perm_${definition.value}`,
      documentType: definition.value,
      onlyIfCreator: false,
      level: 0,
      actions: [...definition.actions],
    })), true)
  }
  const rows: AppRolePermissionRow[] = []
  for (const key of keys || []) {
    const separator = key.lastIndexOf('.')
    if (separator <= 0) continue
    const prefix = key.slice(0, separator)
    const action = key.slice(separator + 1)
    const definition = ROLE_DOCUMENT_TYPES_CACHE.find(item => item.permissionPrefix === prefix)
    if (!definition) continue
    rows.push({
      id: `perm_${definition.value}`,
      documentType: definition.value,
      onlyIfCreator: false,
      level: 0,
      actions: [action],
    })
  }
  return normalizePermissionRows(rows, true)
}

function permissionRowsToFlatKeys(rows: AppRolePermissionRow[]): string[] {
  const definitions = new Map(ROLE_DOCUMENT_TYPES_CACHE.map(item => [item.value, item]))
  const keys = new Set<string>()
  for (const row of rows) {
    const prefix = definitions.get(row.documentType)?.permissionPrefix
    if (!prefix) continue
    for (const action of row.actions || []) keys.add(`${prefix}.${action}`)
  }
  return [...keys].sort()
}

// Seed the matrix catalog used by both adapters.
configureRoleMatrix(
  ROLE_DOCUMENT_TYPES.map(definition => ({
    value: definition.value,
    permissionPrefix: definition.permissionPrefix,
    actions: definition.actions as readonly string[],
  })),
)

function asRecordId(value: unknown): string {
  return value == null ? '' : String(value)
}

function asRoleId(value: unknown): number | undefined {
  if (value == null || value === '') return undefined
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

/** Map backend user fields to the UI column keys (no fabricated data). */
function adaptUserOut(user: Record<string, unknown>): Record<string, unknown> {
  const effectivePermissions = Array.isArray(user.effectivePermissions)
    ? user.effectivePermissions.map(String)
    : []
  const roleId = asRoleId(user.roleId)
  return {
    ...user,
    id: asRecordId(user.id),
    roleId: roleId != null ? String(roleId) : '',
    effectivePermissions,
    permissionRows: permissionRowsFromFlatKeys(effectivePermissions),
    lastLogin: user.lastLoginAt ?? user.lastLogin ?? null,
    // Telegram linking is server-managed; show chat ID when linked.
    telegramUsername: user.telegramLinked
      ? String(user.telegramChatId || 'Linked')
      : '',
  }
}

/** Only the fields UserCreate / UserUpdate accept (`extra="forbid"`). */
function adaptUserIn(input: Record<string, unknown>): Record<string, unknown> {
  const output: Record<string, unknown> = {}
  const username = String(input.username ?? '').trim()
  const displayName = String(input.displayName ?? '').trim()
  const email = String(input.email ?? '').trim()
  const status = String(input.status ?? '').trim()
  const password = String(input.password ?? '')
  const roleId = asRoleId(input.roleId)
  const avatar = typeof input.avatar === 'string'
    ? input.avatar.trim()
    : typeof input.avatarUrl === 'string' ? input.avatarUrl.trim() : ''

  if (username) output.username = username
  if (displayName) output.displayName = displayName
  if (email) output.email = email
  if (status) output.status = status
  if (roleId != null) output.roleId = roleId
  if (password.trim()) output.password = password
  if (avatar) output.avatar = avatar
  return output
}

/** Map backend role fields onto the permission-matrix UI shape. */
function adaptRoleOut(role: Record<string, unknown>): Record<string, unknown> {
  const permissions = Array.isArray(role.permissions) ? role.permissions.map(String) : []
  return {
    ...role,
    id: asRecordId(role.id),
    permissions,
    permissionRows: permissionRowsFromFlatKeys(permissions),
    permissionCount: Number(role.permissionCount ?? permissions.length),
    status: 'Active',
  }
}

/** UI permission-matrix rows â†’ flat backend permission keys. */
function adaptRoleIn(input: Record<string, unknown>): Record<string, unknown> {
  const output = stripUiOnlyFields(input)
  // status is a UI-only column for roles; the backend has no such field.
  delete output.status
  if (Array.isArray(input.permissionRows)) {
    output.permissions = permissionRowsToFlatKeys(input.permissionRows as AppRolePermissionRow[])
  }
  return output
}

/** Backend audit log fields â†’ the audit-logs UI template fields. */
function adaptAuditLogOut(row: Record<string, unknown>): Record<string, unknown> {
  return {
    ...row,
    user: row.userName ?? row.user ?? null,
    entity: row.entityLabel ?? row.entityId ?? '',
    ipDevice: row.ipAddress ?? row.ipDevice ?? '',
  }
}

function adaptProductOut(row: Record<string, unknown>): Record<string, unknown> {
  return {
    ...row,
    id: asRecordId(row.id),
    code: row.code ?? row.sku ?? '',
    sku: row.sku ?? row.code ?? '',
    categoryId: asRecordId(row.categoryId ?? row.category_id) || null,
    brandId: asRecordId(row.brandId ?? row.brand_id) || null,
    uomId: asRecordId(row.uomId ?? row.uom_id) || null,
    category: row.category ?? row.category_name ?? '',
    brand: row.brand ?? row.brand_name ?? '',
    uom: row.uom ?? row.uom_name ?? '',
    uomSymbol: row.uomSymbol ?? row.uom_symbol ?? '',
    costPrice: row.costPrice ?? row.cost_price,
    salePrice: row.salePrice ?? row.selling_price,
    minimumStock: row.minimumStock ?? row.minimum_stock,
    expiryTracking: row.expiryTracking ?? row.expiry_tracking ?? false,
    stockInQty: row.stockInQty ?? row.stock_in_qty,
    stockOutQty: row.stockOutQty ?? row.stock_out_qty,
    damageQty: row.damageQty ?? row.damage_qty,
    imageUrl: row.imageUrl ?? row.image_url ?? null,
    imageObjectKey: row.imageObjectKey ?? row.image_object_key ?? null,
    // Nearest lot expiry for the Stock list column (before Status).
    expiryDate: row.expiryDate ?? row.expiry_date ?? null,
    // UI status dialect (mock + module filters use Active/Inactive).
    status: row.status === 'ACTIVE' ? 'Active' : row.status === 'INACTIVE' ? 'Inactive' : row.status,
    // Pricing rows normalized to the UI camelCase dialect (spec §2.1.3):
    // { uomId, uomSymbol, convertUomId, convertUomSymbol, factorToBase,
    //   salePrice, isDefaultSale, costPrice }.
    uomConversions: adaptUomConversionsOut(row.uomConversions ?? row.uom_conversions),
  }
}

/** Backend Pricing rows (snake or camel) → the UI camelCase row shape. */
function adaptUomConversionsOut(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value
    .filter(row => row && typeof row === 'object')
    .map((row: Record<string, unknown>) => ({
      uomId: asRecordId(row.uomId ?? row.uom_id),
      uomSymbol: row.uomSymbol ?? row.uom_symbol ?? '',
      convertUomId: asRecordId(row.convertUomId ?? row.convert_uom_id) || null,
      convertUomSymbol: row.convertUomSymbol ?? row.convert_uom_symbol ?? '',
      factorToBase: Number(row.factorToBase ?? row.factor_to_base ?? 1),
      salePrice: Number(row.salePrice ?? row.sale_price ?? 0),
      isDefaultSale: row.isDefaultSale === true || row.is_default_sale === true,
      costPrice: row.costPrice != null || row.cost_price != null
        ? Number(row.costPrice ?? row.cost_price)
        : null,
    }))
}

/**
 * Product create/update payload: UI camelCase → ProductCreate/ProductUpdate.
 * Only present keys are forwarded (PATCH is partial). SKU is generated when
 * the UI did not capture one (backend requires a unique sku).
 */
function adaptProductIn(input: Record<string, unknown>): Record<string, unknown> {
  const output: Record<string, unknown> = {}
  const text = (value: unknown): string => String(value ?? '').trim()
  const sku = text(input.sku ?? input.code)
  if (sku) output.sku = sku
  else if (input.id == null && (input.name != null || input.barcode != null)) {
    // Unique-enough fallback: normalized name + timestamp (server re-checks).
    const base = (text(input.name) || text(input.barcode) || 'PRD')
      .toUpperCase().replace(/[^A-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
    output.sku = `${base || 'PRD'}-${Date.now().toString(36).toUpperCase()}`
  }
  if (input.name != null) output.name = text(input.name)
  if (input.barcode != null) output.barcode = text(input.barcode) || null
  if (input.categoryId != null) output.category_id = asRecordId(input.categoryId) || null
  if (input.brandId != null) output.brand_id = asRecordId(input.brandId) || null
  if (input.uomId != null) output.uom_id = asRecordId(input.uomId) || null
  if (input.costPrice != null) output.cost_price = Number(input.costPrice)
  if (input.salePrice != null) output.salePrice = Number(input.salePrice)
  if (input.minimumStock != null) output.minimum_stock = Number(input.minimumStock)
  if (input.expiryTracking != null) output.expiry_tracking = Boolean(input.expiryTracking)
  if (input.note != null) output.note = input.note
  // imageObjectKey is the stored object key; a bare string imageUrl without a
  // scheme is treated as one too (data:/http: URLs are UI-only previews).
  const imageKey = text(input.imageObjectKey)
  const rawImage = text(input.imageUrl)
  if (imageKey) output.image_object_key = imageKey
  else if (rawImage && !/^(data:|https?:)/.test(rawImage)) output.image_object_key = rawImage
  if (input.status != null) {
    const status = text(input.status).toUpperCase()
    output.status = status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE'
  }
  if (Array.isArray(input.uomConversions)) {
    // normalize_uom_conversions on the backend accepts the camelCase rows.
    output.uom_conversions = input.uomConversions
  }
  return output
}

/** UI payment labels → canonical POS tender methods (one mapping, both sides).
 *  Cash→CASH; Card / Mobile Payment / Bank Transfer→BANK_QR (cashless);
 *  Credit→CUSTOMER_DEBT (documented on the backend SaleCreateRequest). */
const POS_PAYMENT_METHOD_MAP: Record<string, string> = {
  Cash: 'CASH',
  Card: 'BANK_QR',
  'Mobile Payment': 'BANK_QR',
  'Bank Transfer': 'BANK_QR',
  Credit: 'CUSTOMER_DEBT',
}

function canonicalPaymentMethod(method: unknown): string {
  return POS_PAYMENT_METHOD_MAP[String(method ?? '').trim()] || String(method ?? 'CASH')
}

function adaptEntityOut(collection: ApiCollection, row: Record<string, unknown>): Record<string, unknown> {
  if (collection === 'users') return adaptUserOut(row)
  if (collection === 'roles') return adaptRoleOut(row)
  if (collection === 'auditLogs') return adaptAuditLogOut(row)
  if (collection === 'products') return adaptProductOut(row)
  if (collection === 'customers' || collection === 'suppliers') return adaptPartyLocationOut(row)
  if (collection === 'customerDebts') return adaptCustomerDebtOut(row)
  if (collection === 'supplierDebts') return adaptSupplierDebtOut(row)
  if (collection === 'deliveryNotes') return adaptDeliveryNoteOut(row)
  if (collection === 'stockMovements') return adaptStockMovementOut(row)
  if (collection === 'sales') return adaptSalesReportLine(row)
  if (collection === 'stockIns') return adaptPurchaseReportLine(row)
  if (collection === 'documentSequences') {
    return {
      ...row,
      nextNumberPreview: documentSequencePreview(row as AppRecord),
    }
  }
  return row
}

/** UI delivery status label ⇄ canonical backend status (one mapping). */
const DELIVERY_STATUS_TO_API: Record<string, string> = {
  Draft: 'DRAFT',
  Confirmed: 'CONFIRMED',
  'Out for Delivery': 'OUT_FOR_DELIVERY',
  Delivered: 'DELIVERED',
  Cancelled: 'CANCELLED',
}

const DELIVERY_STATUS_FROM_API: Record<string, string> = Object.fromEntries(
  Object.entries(DELIVERY_STATUS_TO_API).map(([ui, api]) => [api, ui]),
)

function deliveryStatusLabel(value: unknown): string {
  const raw = String(value ?? '')
  return DELIVERY_STATUS_FROM_API[raw] ?? raw
}

/** Backend DeliveryNoteOut → UI camelCase note shape (multi-invoice, spec §2.1.9). */
function adaptDeliveryNoteOut(row: Record<string, unknown>): Record<string, unknown> {
  const links = Array.isArray(row.sales) ? row.sales as Record<string, unknown>[] : []
  const items = Array.isArray(row.items) ? row.items as Record<string, unknown>[] : []
  const invoiceNos = links.map(link => String(link.invoice_no ?? link.invoiceNo ?? '')).filter(Boolean)
  return {
    ...row,
    id: asRecordId(row.id),
    deliveryNo: row.deliveryNo ?? row.delivery_no ?? '',
    customerId: asRecordId(row.customerId ?? row.customer_id) || null,
    customer: row.customer ?? row.customer_name ?? '',
    // Linked invoices: [{ saleId, invoiceNo }] + joined display keys.
    sales: links.map(link => ({
      saleId: asRecordId(link.saleId ?? link.sale_id),
      invoiceNo: String(link.invoice_no ?? link.invoiceNo ?? ''),
    })),
    invoiceNos,
    invoiceNo: invoiceNos.join(', '),
    saleId: invoiceNos.length === 1 ? String(links[0]?.sale_id ?? links[0]?.saleId ?? '') : '',
    deliveryPhone: row.deliveryPhone ?? row.delivery_phone ?? '',
    deliveryLocation: row.deliveryLocation ?? row.delivery_location ?? '',
    deliveredAt: row.deliveredAt ?? row.delivered_at ?? null,
    status: deliveryStatusLabel(row.status),
    note: row.note ?? null,
    cancelReason: row.cancelReason ?? row.cancel_reason ?? null,
    createdBy: asRecordId(row.createdBy ?? row.created_by),
    createdAt: row.created_at ?? row.createdAt ?? null,
    itemCount: row.itemCount ?? items.length,
    items: items.map(line => ({
      id: asRecordId(line.id),
      saleId: asRecordId(line.saleId ?? line.sale_id),
      saleItemId: asRecordId(line.saleItemId ?? line.sale_item_id),
      productId: asRecordId(line.productId ?? line.product_id),
      product: String(line.product ?? line.product_name ?? ''),
      uomSymbol: String(line.uomSymbol ?? line.uom_symbol ?? ''),
      qtyOrdered: q4(line.qtyOrdered ?? line.qty_ordered),
      qtyToDeliver: q4(line.qtyToDeliver ?? line.qty_to_deliver),
      qtyDelivered: q4(line.qtyDelivered ?? line.qty_delivered),
    })),
  }
}

/** Backend movement row → UI camelCase (Stock Movements page + history dialogs). */
function adaptStockMovementOut(row: Record<string, unknown>): Record<string, unknown> {
  const movementType = String(row.movement_type ?? row.type ?? '')
  const labels: Record<string, string> = {
    STOCK_IN: 'Stock In',
    SALE: 'Sale',
    SALE_RETURN: 'Sale Return',
    PURCHASE_RETURN: 'Purchase Return',
    ADJUSTMENT_IN: 'Adjustment',
    ADJUSTMENT_OUT: 'Adjustment',
    DAMAGE: 'Damage',
    EXPIRE: 'Expiry',
  }
  return {
    ...row,
    id: asRecordId(row.id),
    productId: asRecordId(row.productId ?? row.product_id),
    product: row.product ?? row.product_name ?? '',
    productName: row.productName ?? row.product_name ?? '',
    type: labels[movementType] ?? movementType,
    movementType,
    quantity: Number(row.quantity ?? row.quantity_delta ?? 0),
    quantityDelta: row.quantityDelta ?? row.quantity_delta ?? 0,
    reference: row.reference ?? row.document_no ?? '',
    referenceType: row.referenceType ?? row.reference_type ?? '',
    uom: row.uom ?? row.uom_symbol ?? '',
    uomSymbol: row.uomSymbol ?? row.uom_symbol ?? '',
    user: row.user ?? row.created_by_name ?? '',
    date: row.date ?? row.created_at ?? null,
    createdAt: row.createdAt ?? row.created_at ?? null,
  }
}

/** UI `location` maps to backend `address`; email is not used on parties. */
function adaptPartyLocationOut(row: Record<string, unknown>): Record<string, unknown> {
  const location = String(row.location ?? row.address ?? '').trim()
  return {
    ...row,
    id: asRecordId(row.id),
    location,
    address: location,
  }
}

function adaptPartyLocationIn(input: Record<string, unknown>): Record<string, unknown> {
  const output = stripUiOnlyFields(input)
  const location = String(input.location ?? input.address ?? '').trim()
  output.location = location || null
  output.address = location || null
  delete output.email
  delete output.debtBalance
  delete output.totalDebt
  return output
}

/** Backend customer-debt report row → UI keys (spec 2.1.10 Customer Debt Report). */
function adaptCustomerDebtOut(row: Record<string, unknown>): Record<string, unknown> {
  return {
    id: asRecordId(row.debt_id ?? row.id),
    saleId: row.sale_id ?? null,
    customerId: asRecordId(row.customer_id),
    customer: String(row.customer_name ?? ''),
    customerCode: String(row.customer_code ?? ''),
    invoiceNo: String(row.invoice_no ?? ''),
    date: row.date ?? row.invoice_date ?? row.created_at ?? null,
    invoiceTotal: row.invoice_total ?? null,
    paidAmount: row.paid_amount ?? null,
    remainingAmount: row.remaining_amount ?? null,
    dueDate: row.due_date ?? null,
    status: String(row.status ?? ''),
    createdAt: row.created_at ?? null,
  }
}

/** Backend supplier-debt report row → UI keys (spec 2.1.10 Supplier Debt Report). */
function adaptSupplierDebtOut(row: Record<string, unknown>): Record<string, unknown> {
  return {
    id: asRecordId(row.debt_id ?? row.id),
    stockTransactionId: row.stock_transaction_id ?? null,
    supplierId: asRecordId(row.supplier_id),
    supplier: String(row.supplier_name ?? ''),
    supplierCode: String(row.supplier_code ?? ''),
    purchaseNo: String(row.document_no ?? ''),
    date: row.date ?? row.transaction_date ?? row.created_at ?? null,
    totalAmount: row.total_amount ?? null,
    paidAmount: row.paid_amount ?? null,
    remainingAmount: row.remaining_amount ?? null,
    dueDate: row.due_date ?? null,
    status: String(row.status ?? ''),
    createdAt: row.created_at ?? null,
  }
}

function adaptEntityIn(collection: ApiCollection, input: Record<string, unknown>): Record<string, unknown> {
  if (collection === 'roles') return adaptRoleIn(input)
  if (collection === 'users') return adaptUserIn(input)
  if (collection === 'customers' || collection === 'suppliers') return adaptPartyLocationIn(input)
  if (collection === 'products') return adaptProductIn(input)
  return stripUiOnlyFields(input)
}

/** Round a numeric-ish value to 4 dp (report grouping math). */
function q4(value: unknown): number {
  return Math.round((Number(value ?? 0) + Number.EPSILON) * 10000) / 10000
}

function q2(value: unknown): number {
  return Math.round((Number(value ?? 0) + Number.EPSILON) * 100) / 100
}

/** One backend sales-report line row → camelCase for grouping. */
function adaptSalesReportLine(row: Record<string, unknown>): Record<string, unknown> {
  return {
    saleId: asRecordId(row.sale_id ?? row.saleId),
    saleItemId: asRecordId(row.sale_item_id ?? row.saleItemId),
    productId: asRecordId(row.product_id ?? row.productId) || null,
    date: row.sale_date ?? row.saleDate ?? null,
    invoiceNo: String(row.invoice_no ?? row.invoiceNo ?? ''),
    customer: String(row.customer_name ?? row.customer ?? ''),
    product: String(row.product_name ?? row.product ?? ''),
    quantity: q4(row.quantity),
    returnedQuantity: q4(row.returned_quantity ?? row.returnedQuantity),
    returnableQuantity: q4(row.returnable_quantity ?? row.returnableQuantity),
    price: q2(row.selling_price ?? row.sellingPrice),
    discount: q2(row.discount_amount ?? row.discountAmount),
    total: q2(row.sales_amount ?? row.salesAmount),
    returnAmount: q2(row.return_amount ?? row.returnAmount),
    debtAmount: q2(row.debt_amount ?? row.debtAmount),
    paymentMethod: String(row.payment_method ?? ''),
    cashier: String(row.cashier_name ?? row.cashier ?? ''),
  }
}

/**
 * Group line-level GET /reports/sales rows into document rows matching the
 * UI/mock sale shape (id, saleNo, items[] with returnable quantities) so the
 * Sales Report table AND the customer Return dialog share one contract.
 */
function groupSalesReportRows(rows: Record<string, unknown>[]): AppRecord[] {
  const bySale = new Map<string, Record<string, unknown>>()
  for (const raw of rows) {
    const line = adaptSalesReportLine(raw)
    const key = line.saleId as string
    let doc = bySale.get(key)
    if (!doc) {
      doc = {
        id: key,
        saleNo: line.invoiceNo,
        invoiceNo: line.invoiceNo,
        date: line.date,
        createdAt: line.date,
        customer: line.customer,
        customerId: null,
        items: [],
        lineCount: 0,
        subtotal: 0,
        discount: 0,
        deliveryPrice: 0,
        total: 0,
        returnAmount: 0,
        paidAmount: 0,
        remaining: 0,
        paymentMethod: '',
        cashier: '',
        status: 'Paid',
      }
      bySale.set(key, doc)
    }
    const items = doc.items as Record<string, unknown>[]
    items.push({
      id: line.saleItemId,
      productId: line.productId,
      name: line.product,
      uom: '',
      quantity: line.quantity,
      returnedQuantity: line.returnedQuantity,
      returnableQuantity: line.returnableQuantity,
      price: line.price,
      discount: line.discount,
      total: line.total,
    })
    doc.lineCount = items.length
    doc.subtotal = q2(Number(doc.subtotal) + Number(line.total) + Number(line.discount))
    doc.discount = q2(Number(doc.discount) + Number(line.discount))
    doc.total = q2(Number(doc.total) + Number(line.total))
    doc.returnAmount = q2(Number(doc.returnAmount) + Number(line.returnAmount))
    // Header fields repeat per line — take the first non-empty value.
    if (!doc.paymentMethod && line.paymentMethod) doc.paymentMethod = line.paymentMethod
    if (!doc.cashier && line.cashier) doc.cashier = line.cashier
    doc.remaining = Math.max(Number(doc.remaining), Number(line.debtAmount))
  }
  const docs = [...bySale.values()] as AppRecord[]
  for (const doc of docs) {
    const total = Number(doc.total)
    doc.paidAmount = q2(total - Number(doc.remaining))
    const allReturned = (doc.items as Record<string, unknown>[]).length > 0
      && (doc.items as Record<string, unknown>[]).every(line => q4(line.returnableQuantity) <= 0)
    doc.status = allReturned ? 'Returned' : Number(doc.remaining) > 0
      ? Number(doc.paidAmount) > 0 ? 'Partial' : 'Unpaid'
      : 'Paid'
  }
  // Newest sale first (report rows arrive newest-first already; grouping
  // preserves that order per document).
  return docs
}

/** One backend purchase-report line row → camelCase for grouping. */
function adaptPurchaseReportLine(row: Record<string, unknown>): Record<string, unknown> {
  return {
    transactionId: asRecordId(row.transaction_id ?? row.transactionId),
    itemId: asRecordId(row.stock_transaction_item_id ?? row.stockTransactionItemId),
    productId: asRecordId(row.product_id ?? row.productId) || null,
    date: row.transaction_date ?? row.transactionDate ?? null,
    purchaseNo: String(row.document_no ?? row.documentNo ?? ''),
    supplier: String(row.supplier_name ?? row.supplier ?? ''),
    supplierId: asRecordId(row.supplier_id ?? row.supplierId) || null,
    product: String(row.product_name ?? row.product ?? ''),
    quantity: q4(row.quantity),
    returnedQuantity: q4(row.returned_quantity ?? row.returnedQuantity),
    returnableQuantity: q4(row.returnable_quantity ?? row.returnableQuantity),
    price: q2(row.cost_price ?? row.costPrice),
    total: q2(row.total_cost ?? row.totalCost),
    remaining: q2(row.remaining_debt ?? row.remainingDebt),
    status: String(row.status ?? ''),
  }
}

/**
 * Group line-level GET /reports/purchases rows into document rows matching
 * the UI/mock purchase shape (id, purchaseNo, items[] with returnable qty)
 * so the Purchase Report table AND the supplier Return dialog share one
 * contract. Return lines reference stock_transaction_item_id.
 */
function groupPurchaseReportRows(rows: Record<string, unknown>[]): AppRecord[] {
  const byTx = new Map<string, Record<string, unknown>>()
  for (const raw of rows) {
    const line = adaptPurchaseReportLine(raw)
    const key = line.transactionId as string
    let doc = byTx.get(key)
    if (!doc) {
      doc = {
        id: key,
        purchaseNo: line.purchaseNo,
        date: line.date,
        createdAt: line.date,
        supplier: line.supplier,
        supplierId: line.supplierId,
        items: [],
        lineCount: 0,
        total: 0,
        paidAmount: 0,
        remaining: 0,
        status: 'Completed',
      }
      byTx.set(key, doc)
    }
    const items = doc.items as Record<string, unknown>[]
    items.push({
      id: line.itemId,
      productId: line.productId,
      name: line.product,
      uom: '',
      quantity: line.quantity,
      returnedQuantity: line.returnedQuantity,
      returnableQuantity: line.returnableQuantity,
      price: line.price,
      total: line.total,
    })
    doc.lineCount = items.length
    doc.total = q2(Number(doc.total) + Number(line.total))
    doc.remaining = Math.max(Number(doc.remaining), Number(line.remaining))
    if (!doc.supplier && line.supplier) doc.supplier = line.supplier
  }
  return [...byTx.values()].map((doc) => {
    doc.paidAmount = q2(Number(doc.total) - Number(doc.remaining))
    doc.status = Number(doc.remaining) > 0 ? 'Partial' : 'Completed'
    return doc as AppRecord
  })
}

function statusEndpoint(collection: ApiCollection, id: string): string | null {
  if (collection === 'products') return ApiEndpoints.PRODUCT(id)
  if (collection === 'categories') return ApiEndpoints.CATEGORY(id)
  return null
}

export function createHttpEntityRepository(): EntityRepository {
  const api = useApi()

  /** Report collections are grouped into documents client-side, so fetch a
   *  wide page (line-level rows collapse ~5:1 into document rows). */
  const REPORT_COLLECTIONS = new Set<ApiCollection>(['sales', 'stockIns'])

  async function list(collection: string, query: EntityListQuery = {}): Promise<EntityListResult> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    if (!endpoint) return { items: [], meta: null }
    const key = collection as ApiCollection
    const response = await api.get<unknown>(endpoint, {
      query: {
        ...query,
        limit: query.limit ?? (REPORT_COLLECTIONS.has(key) ? 500 : 100),
      },
      requestKey: `entity-list:${collection}`,
    })
    const items = unwrap<Record<string, unknown>[]>(response)
    const mapped = (Array.isArray(items) ? items : []).map(row => adaptEntityOut(key, row)) as AppRecord[]
    if (key === 'sales') return { items: groupSalesReportRows(mapped as Record<string, unknown>[]), meta: metaOf(response) }
    if (key === 'stockIns') return { items: groupPurchaseReportRows(mapped as Record<string, unknown>[]), meta: metaOf(response) }
    return { items: mapped, meta: metaOf(response) }
  }

  async function get(collection: string, id: string): Promise<AppRecord | null> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    if (!endpoint) return null
    try {
      const response = await api.get<unknown>(`${endpoint}/${id}`, {
        suppressErrorToast: true,
        cancelPrevious: false,
        requestKey: `entity-get:${collection}:${id}`,
      })
      return adaptEntityOut(collection as ApiCollection, unwrap<Record<string, unknown>>(response)) as AppRecord
    }
    catch {
      return null
    }
  }

  async function create(collection: string, input: Record<string, unknown>): Promise<AppRecord> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    const response = await api.post<unknown>(endpoint, adaptEntityIn(collection as ApiCollection, input))
    return adaptEntityOut(collection as ApiCollection, unwrap<Record<string, unknown>>(response)) as AppRecord
  }

  async function update(collection: string, id: string, input: Record<string, unknown>): Promise<AppRecord> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    // Spec §7: the backend uses PATCH for partial updates (no PUT endpoints).
    const response = await api.patch<unknown>(`${endpoint}/${id}`, adaptEntityIn(collection as ApiCollection, input))
    return adaptEntityOut(collection as ApiCollection, unwrap<Record<string, unknown>>(response)) as AppRecord
  }

  async function remove(collection: string, id: string): Promise<void> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    await api.delete(`${endpoint}/${id}`)
  }

  async function setStatus(collection: string, id: string, status: string): Promise<AppRecord> {
    const endpoint = statusEndpoint(collection as ApiCollection, id)
    if (!endpoint) throw new Error(`Status updates are not supported for ${collection}`)
    const response = await api.patch<unknown>(endpoint, { status })
    return adaptEntityOut(collection as ApiCollection, unwrap<Record<string, unknown>>(response)) as AppRecord
  }

  return { list, get, create, update, remove, setStatus }
}

export function createHttpPosCommandRepository(): PosCommandRepository {
  const api = useApi()

  /** camelCase checkout input → POST /pos/sales body (spec §7 POS).
   *  Payment labels map to canonical tender methods: Cash→CASH, Card /
   *  Mobile Payment / Bank Transfer→BANK_QR, Credit→CUSTOMER_DEBT. */
  function saleBody(input: PosCompleteSaleInput): Record<string, unknown> {
    return {
      customer_id: input.customerId || null,
      items: (input.items || []).map(item => ({
        product_id: item.productId,
        quantity: item.quantity,
        ...(item.unitPrice != null ? { unit_price: item.unitPrice } : {}),
        ...(item.discountPercent != null ? { discount_percent: item.discountPercent } : {}),
        ...(item.uomId ? { uom_id: item.uomId } : {}),
        ...(item.uomSymbol ? { uom_symbol: item.uomSymbol } : {}),
        ...(item.factorToBase != null ? { factor_to_base: item.factorToBase } : {}),
      })),
      payment_method: canonicalPaymentMethod(input.paymentMethod),
      amount_received: input.paidAmount,
      discount: input.discount ?? 0,
      note: input.note ?? null,
      included_debt_ids: input.includedDebtIds ?? [],
      delivery_price: input.deliveryPrice ?? 0,
      deposit: input.deposit ?? 0,
    }
  }

  async function completeSale(input: PosCompleteSaleInput): Promise<AppRecord> {
    // Spec §7: checkout posts POST /pos/sales (no /complete suffix).
    return unwrap<Record<string, unknown>>(await api.post<unknown>(
      ApiEndpoints.POS_SALE_COMPLETE,
      saleBody(input),
    )) as AppRecord
  }

  async function createStockOperation(input: Parameters<PosCommandRepository['createStockOperation']>[0]): Promise<AppRecord> {
    // Spec §7 Stock: one create path per operation — never /stock/operations.
    const endpointByType = {
      stock_in: ApiEndpoints.STOCK_IN,
      adjustment: ApiEndpoints.STOCK_ADJUST,
      damage: ApiEndpoints.STOCK_DAMAGE,
      expiry: ApiEndpoints.STOCK_EXPIRE,
    } as const
    const endpoint = endpointByType[input.type]
    if (input.type !== 'stock_in') {
      return unwrap<Record<string, unknown>>(await api.post<unknown>(endpoint, {
        product_id: input.productId,
        quantity: input.quantity,
        note: input.note ?? null,
      })) as AppRecord
    }
    // Stock In = purchase (POST /stock/in): one line per call, qty/cost per
    // the selected Pricing UOM (converted to base server-side); unpaid
    // balance becomes supplier debt in the same transaction.
    const quantity = Number(input.quantity || 0)
    const unitCost = Number(input.unitCost ?? 0)
    const lineTotal = Math.round(quantity * unitCost * 100) / 100
    const paidAmount = input.paidAmount == null ? lineTotal : Math.max(0, Number(input.paidAmount))
    return unwrap<Record<string, unknown>>(await api.post<unknown>(endpoint, {
      ...(input.supplierId ? { supplier_id: input.supplierId } : {}),
      paid_amount: paidAmount,
      payment_method: canonicalPaymentMethod(input.paymentMethod ?? 'Cash') === 'CUSTOMER_DEBT'
        ? 'CASH'
        : canonicalPaymentMethod(input.paymentMethod ?? 'Cash'),
      note: input.note ?? null,
      items: [{
        product_id: input.productId,
        quantity,
        unit_cost: unitCost,
        ...(input.uomId ? { uom_id: input.uomId } : {}),
        ...(input.uomSymbol ? { uom_symbol: input.uomSymbol } : {}),
        ...(input.factorToBase != null ? { factor_to_base: input.factorToBase } : {}),
      }],
    })) as AppRecord
  }

  async function payCustomerDebt(input: Parameters<PosCommandRepository['payCustomerDebt']>[0]): Promise<AppRecord> {
    // Spec §7: POST /customers/{id}/debts/{debt_id}/payments. When the caller
    // has no debt id, the customer-level service endpoint settles open rows.
    const endpoint = input.debtId
      ? ApiEndpoints.CUSTOMER_DEBT_PAYMENTS(input.customerId, input.debtId)
      : ApiEndpoints.CUSTOMER_PAYMENTS(input.customerId)
    return unwrap<Record<string, unknown>>(await api.post<unknown>(endpoint, {
      amount: input.amount,
      payment_method: input.paymentMethod,
      reference: input.reference ?? null,
    })) as AppRecord
  }

  async function paySupplierDebt(input: Parameters<PosCommandRepository['paySupplierDebt']>[0]): Promise<AppRecord> {
    // Spec §7: POST /suppliers/{id}/debts/{debt_id}/payments (same fallback).
    const endpoint = input.debtId
      ? ApiEndpoints.SUPPLIER_DEBT_PAYMENTS(input.supplierId, input.debtId)
      : ApiEndpoints.SUPPLIER_PAYMENTS(input.supplierId)
    return unwrap<Record<string, unknown>>(await api.post<unknown>(endpoint, {
      amount: input.amount,
      payment_method: input.paymentMethod,
      reference: input.reference ?? null,
    })) as AppRecord
  }

  async function getSaleReceipt(saleId: string): Promise<SaleReceipt> {
    const data = unwrap<Record<string, unknown>>(await api.get<unknown>(
      ApiEndpoints.POS_RECEIPT(saleId),
      { requestKey: `pos-receipt:${saleId}`, cancelPrevious: true },
    ))
    const items = (Array.isArray(data.items) ? data.items : []) as Array<Record<string, unknown>>
    return {
      saleId: String(data.sale_id ?? data.saleId ?? saleId),
      saleNo: String(data.sale_no ?? data.saleNo ?? data.invoice_no ?? ''),
      invoiceNo: String(data.invoice_no ?? data.invoiceNo ?? ''),
      date: String(data.sale_date ?? data.date ?? '').slice(0, 10),
      customer: String(data.customer_name ?? data.customer ?? 'Walk-in customer'),
      cashier: String(data.cashier ?? data.created_by_name ?? ''),
      paymentMethod: String(data.payment_method ?? data.paymentMethod ?? ''),
      note: String(data.note ?? ''),
      items: items.map(item => ({
        name: String(item.name ?? item.product_name ?? ''),
        quantity: Number(item.quantity ?? item.qty ?? 0),
        uom: String(item.uom_symbol ?? item.uom ?? ''),
        unitPrice: Number(item.unit_price ?? item.price ?? 0),
        discount: Number(item.discount ?? 0),
        total: Number(item.total ?? item.line_total ?? 0),
      })),
      subtotal: Number(data.subtotal ?? 0),
      discount: Number(data.discount ?? 0),
      deliveryPrice: Number(data.delivery_price ?? data.deliveryPrice ?? 0),
      deposit: Number(data.deposit ?? 0),
      total: Number(data.grand_total ?? data.total ?? 0),
      paidAmount: Number(data.paid_amount ?? data.paid ?? data.paidAmount ?? 0),
      remaining: Number(data.debt_remaining ?? data.remaining ?? data.remaining_amount ?? 0),
    }
  }

  async function returnSale(input: Parameters<PosCommandRepository['returnSale']>[0]): Promise<AppRecord> {
    return unwrap<Record<string, unknown>>(await api.post<unknown>(
      ApiEndpoints.SALE_RETURN(input.saleId),
      {
        reason: input.reason,
        // `items` is the canonical body key; the backend also accepts `lines`.
        items: input.lines.map(line => ({
          sale_item_id: line.lineId,
          quantity: line.quantity,
          restock: line.restock,
        })),
      },
    )) as AppRecord
  }

  async function returnPurchase(input: Parameters<PosCommandRepository['returnPurchase']>[0]): Promise<AppRecord> {
    return unwrap<Record<string, unknown>>(await api.post<unknown>(
      ApiEndpoints.STOCK_IN_RETURN(input.stockInId),
      {
        reason: input.reason,
        lines: input.lines.map(line => ({
          stock_transaction_item_id: line.lineId,
          quantity: line.quantity,
        })),
      },
    )) as AppRecord
  }

  return { completeSale, createStockOperation, payCustomerDebt, paySupplierDebt, getSaleReceipt, returnSale, returnPurchase }
}

/** Backend product-history row → UI camelCase (kind derived from type). */
function adaptProductHistoryOut(row: Record<string, unknown>, kind: StockHistoryKind): ProductHistoryRow {
  return {
    id: String(row.id ?? ''),
    date: String(row.date ?? row.created_at ?? '').slice(0, 10),
    type: String(row.type ?? ''),
    quantity: Number(row.quantity ?? 0),
    reference: String(row.reference ?? row.document_no ?? ''),
    user: String(row.user ?? row.created_by_name ?? ''),
    note: String(row.note ?? ''),
    kind: (row.kind as StockHistoryKind) ?? kind,
  }
}

/** Backend cost-history lot → UI camelCase. */
function adaptCostHistoryOut(row: Record<string, unknown>): ProductCostHistoryRow {
  return {
    id: String(row.id ?? ''),
    date: String(row.date ?? row.created_at ?? '').slice(0, 10),
    product: String(row.product ?? row.product_name ?? ''),
    unitCost: Number(row.unit_cost ?? row.unitCost ?? 0),
    quantity: Number(row.quantity ?? 0),
    amount: Number(row.amount ?? row.line_amount ?? 0),
    version: Number(row.version ?? 0),
    documentNo: String(row.document_no ?? row.documentNo ?? ''),
  }
}

/** Backend sale-price version → UI camelCase. */
function adaptSalePriceOut(row: Record<string, unknown>): ProductSalePriceRow {
  return {
    id: String(row.id ?? row.price_id ?? ''),
    productId: String(row.product_id ?? row.productId ?? ''),
    product: String(row.product ?? row.product_name ?? ''),
    salePrice: Number(row.sale_price ?? row.salePrice ?? 0),
    date: String(row.date ?? row.created_at ?? '').slice(0, 10),
    isActive: row.is_active === true || row.isActive === true,
    version: Number(row.version ?? 0),
  }
}

/**
 * HTTP implementation of the product-scoped dialog queries. Each method hits
 * the product-scoped /api/v1 URL so HTTP mode never downloads unrelated
 * collections (spec §7 Stock).
 */
export function createHttpStockQueryRepository(): StockQueryRepository {
  const api = useApi()

  return {
    async listProductHistory(productId, query = {}): Promise<EntityListResult<ProductHistoryRow>> {
      const kind: StockHistoryKind = query.type ?? 'stock_in'
      const response = await api.get<unknown>(ApiEndpoints.PRODUCT_HISTORY(productId), {
        query: {
          // Backend expects snake_case movement kinds.
          type: kind,
          q: query.q,
          start_date: query.startDate,
          end_date: query.endDate,
          page: query.page,
          limit: query.limit,
        },
        requestKey: `product-history:${productId}`,
        cancelPrevious: true,
      })
      const rows = unwrap<Record<string, unknown>[]>(response)
      return {
        items: (Array.isArray(rows) ? rows : []).map(row => adaptProductHistoryOut(row, kind)),
        meta: metaOf(response),
      }
    },

    async listProductCostHistory(productId, query = {}): Promise<EntityListResult<ProductCostHistoryRow>> {
      const response = await api.get<unknown>(ApiEndpoints.PRODUCT_COST_HISTORY(productId), {
        query: {
          q: query.q,
          start_date: query.startDate,
          end_date: query.endDate,
          page: query.page,
          limit: query.limit,
        },
        requestKey: `product-cost-history:${productId}`,
        cancelPrevious: true,
      })
      const rows = unwrap<Record<string, unknown>[]>(response)
      return {
        items: (Array.isArray(rows) ? rows : []).map(adaptCostHistoryOut),
        meta: metaOf(response),
      }
    },

    async listSalePrices(productId, query = {}): Promise<EntityListResult<ProductSalePriceRow>> {
      const response = await api.get<unknown>(ApiEndpoints.PRODUCT_SALE_PRICES(productId), {
        query: {
          q: query.q,
          start_date: query.startDate,
          end_date: query.endDate,
          page: query.page,
          limit: query.limit,
        },
        requestKey: `product-sale-prices:${productId}`,
        cancelPrevious: true,
      })
      const rows = unwrap<Record<string, unknown>[]>(response)
      return {
        items: (Array.isArray(rows) ? rows : []).map(adaptSalePriceOut),
        meta: metaOf(response),
      }
    },

    async addSalePrice(productId, input): Promise<ProductSalePriceRow> {
      const response = await api.post<unknown>(ApiEndpoints.PRODUCT_SALE_PRICES(productId), {
        date: input.date,
        sale_price: input.salePrice,
      })
      return adaptSalePriceOut(unwrap<Record<string, unknown>>(response))
    },

    async activateSalePrice(productId, priceId): Promise<ProductSalePriceRow> {
      const response = await api.post<unknown>(ApiEndpoints.PRODUCT_SALE_PRICE_ACTIVATE(productId, priceId), {})
      return adaptSalePriceOut(unwrap<Record<string, unknown>>(response))
    },
  }
}

export function createHttpFinanceRepository(): FinanceRepository {
  const api = useApi()

  return {
    /**
     * Maps the GET /api/v1/dashboard/summary payload (nested `cards`,
     * `chart`, `summary`, `extras` blocks) into the flat DashboardSummary
     * contract. Passes `period=custom` so the backend honors the requested
     * date range; without dates the backend defaults to the last 7 days.
     */
    async dashboard(startDate?: string, endDate?: string, requestKey = 'dashboard'): Promise<DashboardSummary> {
      const data = unwrap<Record<string, unknown>>(await api.get<unknown>(ApiEndpoints.DASHBOARD, {
        query: {
          period: startDate && endDate ? 'custom' : undefined,
          startDate,
          endDate,
        },
        requestKey,
        cancelPrevious: true,
      }))
      const cards = (data.cards ?? {}) as Record<string, unknown>
      const summary = (data.summary ?? {}) as Record<string, unknown>
      const extras = (data.extras ?? {}) as Record<string, unknown>
      const chart = (Array.isArray(data.chart) ? data.chart : []) as Array<Record<string, unknown>>
      const num = (value: unknown): number => Number(value ?? 0)
      const numOrNull = (value: unknown): number | null => (value === null || value === undefined ? null : Number(value))
      const day = (value: unknown): string => String(value ?? '').slice(0, 10)
      return {
        productsTotal: num(cards.total_products),
        lowStockCount: num(extras.low_stock_count),
        outOfStockCount: num(extras.out_of_stock_count),
        salesToday: num(cards.today_sales_count),
        salesTodayAmount: num(cards.today_sales),
        salesThisMonth: num(summary.sales_this_month_count),
        salesThisMonthAmount: num(summary.sales_this_month_amount),
        income: num(summary.total_income),
        expense: num(summary.total_expense),
        grossProfit: numOrNull(summary.gross_profit),
        netIncome: numOrNull(summary.net_income),
        customerDebt: num(summary.customer_debt),
        supplierDebt: num(summary.supplier_debt),
        damageLoss: num(summary.damage_loss),
        expiryLoss: num(summary.expiry_loss),
        pendingDeliveryNotes: num(summary.pending_delivery_notes_count),
        salesByDay: chart.map(row => ({ date: day(row.date), count: num(row.sales_count) })),
        incomeByDay: chart.map(row => ({ date: day(row.date), amount: num(row.income) })),
        expenseByDay: chart.map(row => ({ date: day(row.date), amount: num(row.expense) })),
        startDate: data.period_start ? day(data.period_start) : startDate ?? null,
        endDate: data.period_end ? day(data.period_end) : endDate ?? null,
      }
    },
    async financeSummary(startDate?: string, endDate?: string): Promise<FinanceSummary> {
      // Canonical spec path GET /reports/finance; fall back to the /summary
      // alias for backends that still expose it.
      let data: Record<string, unknown>
      try {
        data = unwrap<Record<string, unknown>>(await api.get<unknown>(ApiEndpoints.FINANCE, {
          query: { startDate, endDate },
          requestKey: 'finance-summary',
          cancelPrevious: true,
          suppressErrorToast: true,
        }))
      }
      catch (error: unknown) {
        if ((error as { statusCode?: number })?.statusCode !== 404) throw error
        data = unwrap<Record<string, unknown>>(await api.get<unknown>(ApiEndpoints.FINANCE_SUMMARY, {
          query: { startDate, endDate },
          requestKey: 'finance-summary',
          cancelPrevious: true,
        }))
      }
      return {
        income: Number(data.income ?? data.total_income ?? 0),
        expense: Number(data.expense ?? data.total_expense ?? 0),
        net: Number(data.net ?? data.net_result ?? 0),
        outstanding: Number(data.outstanding ?? data.outstanding_debt ?? 0),
        startDate: (data.startDate ?? data.start_date ?? startDate) ? String(data.startDate ?? data.start_date ?? startDate).slice(0, 10) : null,
        endDate: (data.endDate ?? data.end_date ?? endDate) ? String(data.endDate ?? data.end_date ?? endDate).slice(0, 10) : null,
      }
    },
    async entries(startDate?: string, endDate?: string): Promise<FinanceEntry[]> {
      const data = unwrap<unknown[]>(await api.get<unknown>(ApiEndpoints.FINANCE_ENTRIES, {
        query: { startDate, endDate },
        requestKey: 'finance-entries',
        cancelPrevious: true,
      }))
      return (Array.isArray(data) ? data : []).map(row => normalizeFinanceEntry(row as Record<string, unknown>))
    },
    async createExpense(input: Parameters<FinanceRepository['createExpense']>[0]): Promise<FinanceEntry> {
      const data = unwrap<Record<string, unknown>>(await api.post<unknown>(
        ApiEndpoints.FINANCE_EXPENSES,
        {
          date: input.date,
          category: input.category,
          description: input.description,
          amount: input.amount,
          payment_method: input.paymentMethod,
          reference: input.reference ?? null,
        },
      ))
      return normalizeFinanceEntry(data)
    },
  }
}

function normalizeFinanceEntry(row: Record<string, unknown>): FinanceEntry {
  const rawType = String(row.type ?? '').toLowerCase()
  return {
    id: String(row.id || ''),
    date: String(row.date || row.entry_date || '').slice(0, 10),
    type: rawType === 'expense' ? 'expense' : 'income',
    reference: String(row.reference || row.document_no || ''),
    category: String(row.category || ''),
    description: String(row.description || ''),
    amount: Number(row.amount || 0),
    paymentMethod: String(row.paymentMethod || row.payment_method || ''),
    user: String(row.user || row.created_by_name || ''),
  }
}

export function createHttpSearchRepository(): SearchRepository {
  const api = useApi()

  return {
    async search(q: string, limit = 12): Promise<SearchHitItem[]> {
      const data = unwrap<{ hits?: SearchHitItem[], total?: number }>(await api.get<unknown>(ApiEndpoints.SEARCH, {
        query: { q, limit },
        requestKey: 'search-keyword',
        cancelPrevious: true,
      }))
      return (data?.hits || []).map(hit => ({
        id: String(hit.id),
        type: String(hit.type),
        title: String(hit.title),
        subtitle: hit.subtitle ?? null,
        url: String(hit.url),
      }))
    },
  }
}
