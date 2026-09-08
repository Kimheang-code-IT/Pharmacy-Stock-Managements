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
    category: row.category ?? row.category_name ?? '',
    brand: row.brand ?? row.brand_name ?? '',
    uom: row.uom ?? row.uom_name ?? '',
    uomSymbol: row.uomSymbol ?? row.uom_symbol ?? '',
    costPrice: row.costPrice ?? row.cost_price,
    salePrice: row.salePrice ?? row.selling_price,
    stockInQty: row.stockInQty ?? row.stock_in_qty,
    stockOutQty: row.stockOutQty ?? row.stock_out_qty,
    damageQty: row.damageQty ?? row.damage_qty,
    imageUrl: row.imageUrl ?? row.image_url ?? null,
    expiryTracking: row.expiryTracking ?? row.expiry_tracking ?? false,
    // Nearest lot expiry for the Stock list column (before Status).
    expiryDate: row.expiryDate ?? row.expiry_date ?? null,
  }
}

function adaptEntityOut(collection: ApiCollection, row: Record<string, unknown>): Record<string, unknown> {
  if (collection === 'users') return adaptUserOut(row)
  if (collection === 'roles') return adaptRoleOut(row)
  if (collection === 'auditLogs') return adaptAuditLogOut(row)
  if (collection === 'products') return adaptProductOut(row)
  if (collection === 'customers' || collection === 'suppliers') return adaptPartyLocationOut(row)
  if (collection === 'customerDebts') return adaptCustomerDebtOut(row)
  if (collection === 'supplierDebts') return adaptSupplierDebtOut(row)
  if (collection === 'documentSequences') {
    return {
      ...row,
      nextNumberPreview: documentSequencePreview(row as AppRecord),
    }
  }
  return row
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
  return stripUiOnlyFields(input)
}

function statusEndpoint(collection: ApiCollection, id: string): string | null {
  if (collection === 'products') return ApiEndpoints.PRODUCT(id)
  if (collection === 'categories') return ApiEndpoints.CATEGORY(id)
  return null
}

export function createHttpEntityRepository(): EntityRepository {
  const api = useApi()

  async function list(collection: string, query: EntityListQuery = {}): Promise<EntityListResult> {
    const endpoint = CollectionEndpoints[collection as ApiCollection]
    if (!endpoint) return { items: [], meta: null }
    const response = await api.get<unknown>(endpoint, {
      query: { ...query, limit: query.limit ?? 100 },
      requestKey: `entity-list:${collection}`,
    })
    const items = unwrap<Record<string, unknown>[]>(response)
    return {
      items: (Array.isArray(items) ? items : []).map(row => adaptEntityOut(collection as ApiCollection, row)) as AppRecord[],
      meta: metaOf(response),
    }
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

  /** camelCase checkout input → snake_case POST /pos/sales body (spec §7 POS). */
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
      payment_method: input.paymentMethod,
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
    const body: Record<string, unknown> = {
      product_id: input.productId,
      quantity: input.quantity,
      note: input.note ?? null,
    }
    if (input.type === 'stock_in') {
      if (input.uomId) body.uom_id = input.uomId
      if (input.uomSymbol) body.uom_symbol = input.uomSymbol
      if (input.factorToBase != null) body.factor_to_base = input.factorToBase
      if (input.unitCost != null) body.unit_cost = input.unitCost
    }
    return unwrap<Record<string, unknown>>(await api.post<unknown>(endpoint, body)) as AppRecord
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
      saleNo: String(data.sale_no ?? data.saleNo ?? ''),
      invoiceNo: String(data.invoice_no ?? data.invoiceNo ?? ''),
      date: String(data.date ?? '').slice(0, 10),
      customer: String(data.customer_name ?? data.customer ?? 'Walk-in customer'),
      cashier: String(data.cashier ?? data.created_by_name ?? ''),
      paymentMethod: String(data.payment_method ?? data.paymentMethod ?? ''),
      note: String(data.note ?? ''),
      items: items.map(item => ({
        name: String(item.name ?? item.product_name ?? ''),
        quantity: Number(item.quantity ?? 0),
        uom: String(item.uom_symbol ?? item.uom ?? ''),
        unitPrice: Number(item.unit_price ?? item.price ?? 0),
        discount: Number(item.discount ?? 0),
        total: Number(item.total ?? item.line_total ?? 0),
      })),
      subtotal: Number(data.subtotal ?? 0),
      discount: Number(data.discount ?? 0),
      deliveryPrice: Number(data.delivery_price ?? data.deliveryPrice ?? 0),
      deposit: Number(data.deposit ?? 0),
      total: Number(data.total ?? 0),
      paidAmount: Number(data.paid_amount ?? data.paidAmount ?? 0),
      remaining: Number(data.remaining ?? data.remaining_amount ?? 0),
    }
  }

  async function returnSale(input: Parameters<PosCommandRepository['returnSale']>[0]): Promise<AppRecord> {
    return unwrap<Record<string, unknown>>(await api.post<unknown>(
      ApiEndpoints.SALE_RETURN(input.saleId),
      {
        reason: input.reason,
        lines: input.lines.map(line => ({
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
