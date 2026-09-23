/**
 * Product UOM conversion / Pricing helpers (spec §2.1.3: the product document
 * **Pricing** tab edits the same `uomConversions` data — there is no separate
 * Convert UOM tab).
 *
 * Row shape (spec products.uom_conversions): `{ uomId, uomSymbol,
 * convertUomId, convertUomSymbol, factorToBase, salePrice, isDefaultSale,
 * costPrice? }`. **Original UOM** = `uomId` (the POS-selectable sell unit,
 * unique per product, base UOM row included). **Convert UOM** defaults to the
 * product base UOM from General. Exactly one row per product has
 * `isDefaultSale = true`.
 *
 * All quantities/money math here is decimal-safe: values are parsed as
 * decimal strings and multiplied as scaled BigInt integers, so factors like
 * `1.5` never accumulate binary-float drift. The final conversion to a
 * `number` happens once, from an exact decimal string.
 */

/** Pricing row stored on a product record (spec §2.1.3). */
export type UomConversion = {
  /** Original UOM — the sell unit the cashier selects on POS. */
  uomId: string
  /** UOM symbol snapshot for display (Stock In / POS selectors). */
  uomSymbol: string
  /** Target / stock UOM — defaults to the product base UOM. */
  convertUomId: string
  /** Convert UOM symbol snapshot. */
  convertUomSymbol: string
  /** How many Convert UOM units 1 of the Original UOM contains (> 0; base row = 1). */
  factorToBase: number
  /** Sale price per Original UOM (required, > 0). */
  salePrice: number
  /** Exactly one row per product is the POS default sale. Not shown in the
   *  product form — save-time normalization always flags the base row. */
  isDefaultSale?: boolean
  /** Cost per this UOM; `null` = derived from base cost × factor on save. */
  costPrice: number | null
  /** POS-active flag: inactive rows are hidden from the POS cart (default true). */
  isActive?: boolean
}

const MAX_SCALE = 6

function parseDecimal(value: unknown): { negative: boolean, digits: bigint, scale: number } | null {
  const text = String(value ?? '').trim()
  if (!/^-?\d*(\.\d*)?$/.test(text) || text === '' || text === '-' || text === '.') return null
  const negative = text.startsWith('-')
  const unsigned = negative ? text.slice(1) : text
  const [intPart = '', fracPart = ''] = unsigned.split('.')
  const digits = BigInt(`${intPart || '0'}${fracPart}` || '0')
  return { negative, digits, scale: fracPart.length }
}

function scaledToNumber(digits: bigint, scale: number): number {
  // Round half-up (by magnitude) to MAX_SCALE decimals using integer math.
  let sign = 1n
  let value = digits
  if (value < 0n) {
    sign = -1n
    value = -value
  }
  if (scale > MAX_SCALE) {
    const drop = BigInt(10) ** BigInt(scale - MAX_SCALE)
    const half = drop / 2n
    value = (value + half) / drop
    scale = MAX_SCALE
  }
  const result = Number(value * sign) / 10 ** scale
  return Object.is(result, -0) ? 0 : result
}

/** Decimal-safe `a × b` — no binary-float drift (e.g. `1.1 × 3` is exactly 3.3). */
export function multiplyDecimalSafe(a: unknown, b: unknown): number {
  const da = parseDecimal(a)
  const db = parseDecimal(b)
  if (!da || !db) return 0
  const negative = da.negative !== db.negative
  const digits = da.digits * db.digits * (negative ? -1n : 1n)
  return scaledToNumber(digits, da.scale + db.scale)
}

/** Decimal-safe `a ÷ b` — exact while the quotient fits MAX_SCALE decimals. */
export function divideDecimalSafe(a: unknown, b: unknown): number {
  const da = parseDecimal(a)
  const db = parseDecimal(b)
  if (!da || !db || db.digits === 0n) return 0
  const negative = da.negative !== db.negative
  // Scale the dividend up enough to keep MAX_SCALE decimals of quotient.
  const scaleBoost = Math.max(0, MAX_SCALE + db.scale - da.scale)
  const digits = (da.digits * BigInt(10) ** BigInt(scaleBoost)) / db.digits
  return scaledToNumber(negative ? -digits : digits, da.scale + scaleBoost - db.scale)
}

/** Quantize a value to the shared decimal scale (trims float noise, e.g. 24.000000001 → 24). */
export function roundQty(value: unknown): number {
  return multiplyDecimalSafe(value, 1)
}

/** Convert a quantity in a UOM to the product base UOM (`qty × factor`). */
export function convertToBase(qty: unknown, factorToBase: unknown): number {
  return multiplyDecimalSafe(qty, factorToBase)
}

/**
 * Value to show for a stored `factorToBase` in the chosen entry direction.
 *
 * Forward = "1 Original = N Convert" (the stored factor itself); reverse =
 * "1 Convert = N Original" (its reciprocal). The stored factor is unchanged —
 * direction is a Pricing-tab input/display convenience only.
 */
export function factorForDirection(factorToBase: unknown, reverse: boolean): number {
  return reverse ? divideDecimalSafe(1, factorToBase) : roundQty(factorToBase)
}

/** Stored `factorToBase` for a value typed in the chosen entry direction. */
export function factorFromDirection(value: unknown, reverse: boolean): number {
  if (!reverse) return roundQty(value)
  const typed = Number(value)
  if (!Number.isFinite(typed) || typed <= 0) return 0
  return divideDecimalSafe(1, typed)
}

/**
 * Round a conversion factor for display: a reciprocal like `1/0.083333`
 * becomes `12` instead of `12.000048`, and other values keep at most 4
 * decimals. Stored factors are never changed by this.
 */
export function cleanConversionFactor(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  const rounded = Math.round(n * 10000) / 10000
  const nearest = Math.round(rounded)
  return Math.abs(rounded - nearest) < 1e-3 ? nearest : rounded
}

function asConversionRow(row: Record<string, unknown>): UomConversion {
  return {
    uomId: String(row.uomId ?? '').trim(),
    uomSymbol: String(row.uomSymbol ?? '').trim(),
    convertUomId: String(row.convertUomId ?? '').trim(),
    convertUomSymbol: String(row.convertUomSymbol ?? '').trim(),
    factorToBase: multiplyDecimalSafe(row.factorToBase ?? 1, 1),
    costPrice: row.costPrice == null || row.costPrice === '' ? null : Number(row.costPrice),
    salePrice: Number(row.salePrice ?? 0),
    isDefaultSale: row.isDefaultSale === true || row.isDefaultSale === 'true',
    isActive: row.isActive !== false && row.is_active !== false,
  }
}

/**
 * Validate + normalize a product's Pricing rows.
 *
 * Rules (spec §2.1.3): Original UOM required and unique per product (the
 * base UOM row is allowed and pinned to factor 1), factor > 0, sale price
 * > 0 (every Pricing row is sellable on POS), Convert UOM defaults to the
 * product base UOM, exactly one `isDefaultSale` (the base row when nothing
 * is marked; the first marked row wins when several). A missing base row is
 * synthesized from `opts.baseSalePrice` (symbol from `opts.baseUomSymbol`)
 * so the product always keeps at least one sellable row. Empty cost prices
 * are **derived and persisted** (`baseCost × factor`) so Stock In can always
 * read a concrete cost.
 */
export function normalizeUomConversions(
  rows: unknown,
  baseUomId: string,
  opts: { baseCostPrice?: number | string, baseSalePrice?: number | string, baseUomSymbol?: string } = {},
): UomConversion[] {
  const baseSymbol = String(opts.baseUomSymbol ?? '')
  const list = Array.isArray(rows) ? rows as Array<Record<string, unknown>> : []
  const out: UomConversion[] = []
  for (const raw of list) {
    const row = asConversionRow(raw)
    if (!row.uomId) throw new Error('Pricing UOM is required')
    if (out.some(item => item.uomId === row.uomId)) {
      throw new Error('Duplicate Pricing UOM — each UOM may appear once per product')
    }
    const isBase = Boolean(baseUomId) && row.uomId === String(baseUomId)
    if (isBase) {
      // A base=base row is always exactly 1.
      row.factorToBase = 1
    }
    else if (!(row.factorToBase > 0)) {
      throw new Error('Conversion qty must be greater than zero')
    }
    if (!(row.salePrice > 0)) {
      throw new Error('Sale price must be greater than zero for every Pricing row')
    }
    row.convertUomId = row.convertUomId || String(baseUomId || '')
    row.convertUomSymbol = row.convertUomSymbol || (row.convertUomId === String(baseUomId || '') ? baseSymbol : '')
    row.uomSymbol = row.uomSymbol || (isBase ? baseSymbol : '')
    if (!isBase && baseUomId && row.convertUomId === row.uomId) {
      throw new Error('Convert UOM must differ from the Original UOM')
    }
    const costPrice = row.costPrice != null
      ? Math.max(0, row.costPrice)
      : multiplyDecimalSafe(opts.baseCostPrice ?? 0, row.factorToBase)
    out.push({ ...row, costPrice })
  }
  if (out.length) {
    // Materialize a missing base row (spec §2.1.3: keep at least one sellable
    // row, typically base) from the POS-active sale price + base cost.
    if (!out.some(row => row.uomId === String(baseUomId || '')) && opts.baseSalePrice != null && Number(opts.baseSalePrice) > 0) {
      out.unshift({
        uomId: String(baseUomId || ''),
        uomSymbol: baseSymbol,
        convertUomId: String(baseUomId || ''),
        convertUomSymbol: baseSymbol,
        factorToBase: 1,
        salePrice: Number(opts.baseSalePrice),
        isDefaultSale: false,
        costPrice: null,
        isActive: true,
      })
    }
    // Exactly one default-sale row: the marked row, else the base row, else
    // the first row — every other row is explicitly false (spec §2.1.3).
    let defaultIndex = out.findIndex(row => row.isDefaultSale)
    if (defaultIndex === -1) defaultIndex = out.findIndex(row => row.uomId === String(baseUomId))
    if (defaultIndex === -1) defaultIndex = 0
    out.forEach((row, index) => {
      row.isDefaultSale = index === defaultIndex
    })
  }
  return out
}

/** Whole "big" units + leftover in the smallest UOM (e.g. 5 + 10 pieces). */
export interface StockBreakdown {
  whole: number
  leftover: number
  smallSymbol: string
  bigSymbol: string
}

/**
 * Express a base-UOM stock quantity as whole "big" units plus the leftover in
 * the smallest configured UOM. Works in both directions:
 * - base is the big UOM (e.g. 5.83 units, 1 unit = 12 pcs) → `5 + 10 pcs`
 * - base is the small UOM (e.g. 70 pcs, 1 box = 12 pcs) → `5 + 10 pcs`
 *
 * Returns null when the product has fewer than two distinct UOMs (nothing to
 * break down), so callers fall back to the plain quantity.
 */
export function stockBreakdown(
  baseStock: unknown,
  product: Record<string, unknown> | null | undefined,
): StockBreakdown | null {
  const rows = pricingRowsFor(product)
  if (!rows.length) return null
  const baseId = String(product?.uomId ?? '')
  const candidates = [
    { factor: 1, symbol: String(product?.uomSymbol ?? '') },
    ...rows
      .filter(row => row.uomId && row.uomId !== baseId)
      .map(row => ({ factor: Number(row.factorToBase) || 1, symbol: String(row.uomSymbol || '') })),
  ].filter(item => item.factor > 0)
  if (candidates.length < 2) return null
  const small = candidates.reduce((a, b) => (b.factor < a.factor ? b : a))
  const big = candidates.reduce((a, b) => (b.factor > a.factor ? b : a))
  if (small.factor === big.factor) return null

  const total = Number(baseStock) || 0
  const ratio = big.factor / small.factor
  let whole = Math.floor(total / big.factor)
  const leftoverBase = total - whole * big.factor
  let leftover = Math.round(leftoverBase / small.factor)
  // A rounded remainder that fills a whole big unit carries over.
  if (leftover >= ratio - 1e-9) {
    whole += 1
    leftover = 0
  }
  return { whole, leftover, smallSymbol: small.symbol, bigSymbol: big.symbol }
}

/** Trim long fractions (5.8333 → 5.83) for compact stock labels. */
export function formatStockQuantity(value: unknown): string {
  const rounded = Math.round((Number(value) || 0) * 100) / 100
  return String(rounded)
}

/**
 * Stock label used everywhere a product quantity is shown: the
 * whole-units + leftover breakdown when a UOM conversion exists (e.g.
 * `5 + 10 បន្ទះ`), else the cleaned quantity.
 */
export function stockBreakdownLabel(
  baseStock: unknown,
  product: Record<string, unknown> | null | undefined,
): string {
  const parts = stockBreakdown(baseStock, product)
  if (!parts) return formatStockQuantity(baseStock)
  if (parts.leftover <= 0) return String(parts.whole)
  return `${parts.whole} + ${parts.leftover} ${parts.smallSymbol}`.trim()
}

/** All Pricing rows of a product (empty for products without pricing). */
export function pricingRowsFor(product: Record<string, unknown> | null | undefined): UomConversion[] {
  if (!product) return []
  const rows = Array.isArray(product.uomConversions) ? product.uomConversions as Array<Record<string, unknown>> : []
  return rows.map(asConversionRow)
}

/** Find a product's Pricing row for a UOM (null = no row for that UOM). */
export function conversionForUom(product: Record<string, unknown> | null | undefined, uomId: string): UomConversion | null {
  if (!product || !uomId) return null
  return pricingRowsFor(product).find(row => row.uomId === String(uomId)) || null
}

/** The row flagged Default sale, else the base/first row — POS pre-select (spec §2.1.3). */
export function defaultSaleRow(product: Record<string, unknown> | null | undefined): UomConversion | null {
  const rows = pricingRowsFor(product)
  if (!rows.length) return null
  // Prefer POS-active rows so a deactivated default never starts a cart line.
  const active = rows.filter(row => row.isActive !== false)
  const pool = active.length ? active : rows
  return pool.find(row => row.isDefaultSale)
    || pool.find(row => row.uomId === String(product?.uomId ?? ''))
    || pool[0]!
}

/**
 * Unit price for a UOM: the Pricing row's sale price, else the base sale
 * price. The product's **base UOM** always resolves to the POS-active mirror
 * `product.salePrice` — activating a sale-price version copies the price
 * there first, so POS add-to-cart / UOM switch / cart sync pick it up
 * immediately even when the stored base Pricing row holds a stale snapshot.
 */
export function salePriceForUom(product: Record<string, unknown> | null | undefined, uomId: string): number | null {
  if (!product) return null
  if (uomId && String(product.uomId ?? '') === String(uomId)) return Number(product.salePrice ?? 0)
  const conversion = conversionForUom(product, uomId)
  if (conversion) return conversion.salePrice
  return null
}

/**
 * One sale-price version / batch scope selected in the Pricing tab and loaded
 * into the Pricing table. UI state only — never POSTed with the product.
 *
 * - `scope: 'general'` (or null selection) → live product `uomConversions`
 * - `scope: 'batch'` → batch-scoped draft; Save creates a new sale-price version
 */
export interface SalePriceVersionSelection {
  id: string
  version: number
  /** Batch/lot scope; null = general pricing (all lots). */
  batchNo: string | null
  /** General product price vs a stock-lot batch scope. */
  scope: 'general' | 'batch'
  /** Exactly one POS-active version per product + batch scope. */
  isActive: boolean
  /** Version-level (default-sale) price mirror. */
  salePrice: number
  /** Lot expiry when the selection is batch-scoped. */
  expiryDate?: string | null
  /** When true, Pricing-table edits update this draft (batch scope). */
  editable?: boolean
  /** UOM price rows inside the version / draft. */
  uomPrices: Array<{
    uomId: string
    uomSymbol?: string | null
    factorToBase: number
    salePrice: number
    isDefaultSale?: boolean
    /** POS-active flag of the UOM row (default true). */
    isActive?: boolean
  }>
}

/** Build the Pricing-tab selection payload from a version-history row. */
export function salePriceVersionSelection(row: {
  id: string
  version: number
  batchNo?: string | null
  isActive?: boolean
  salePrice?: number
  expiryDate?: string | null
  uomPrices?: SalePriceVersionSelection['uomPrices']
  scope?: 'general' | 'batch'
  editable?: boolean
}): SalePriceVersionSelection {
  const batchNo = row.batchNo ?? null
  const scope = row.scope ?? (batchNo ? 'batch' : 'general')
  return {
    id: String(row.id ?? ''),
    version: Number(row.version ?? 0),
    batchNo,
    scope,
    isActive: row.isActive === true,
    salePrice: Number(row.salePrice ?? 0),
    expiryDate: row.expiryDate ?? null,
    editable: row.editable ?? scope === 'batch',
    uomPrices: Array.isArray(row.uomPrices) ? row.uomPrices.map(uom => ({ ...uom })) : [],
  }
}

/** One Pricing-tab batch rail card (General or a stock lot). */
export type BatchPricingCard = {
  key: string
  scope: 'general' | 'batch'
  batchNo: string | null
  label: string
  expiryDate: string | null
  remainingQty: number | null
  unitCost: number | null
  lotStatus: string | null
  /** POS-active sale-price version for this scope (if any). */
  priceId: string | null
  priceVersion: number | null
  isPriceActive: boolean
  salePrice: number | null
  uomPrices: SalePriceVersionSelection['uomPrices']
  /** Base-UOM sale price used for the gross value (active row, else fallback). */
  unitSalePrice: number | null
  /** Gross value of the lot: remaining base qty × base-UOM sale price. */
  grossValue: number | null
}

/**
 * Build rail cards: always General first, then stock lots joined to the
 * newest/active sale-price version for that `batchNo`.
 */
/** Base-UOM sale price of a card's POS-active price rows (fallback: any row). */
function baseUnitSalePrice(
  uomPrices: SalePriceVersionSelection['uomPrices'],
  baseUomId: string | undefined,
  fallback: number | null,
): number | null {
  const active = uomPrices.filter(uom => uom.isActive !== false)
  const pool = active.length ? active : uomPrices
  if (!pool.length) return fallback
  const base = pool.find(uom => String(uom.uomId) === String(baseUomId ?? ''))
  const price = Number((base ?? pool[0]!).salePrice)
  return Number.isFinite(price) ? price : fallback
}

export function buildBatchPricingCards(input: {
  lots: Array<{
    batchNo: string
    expiryDate?: string | null
    remainingQty?: number
    unitCost?: number
    status?: string
  }>
  salePrices: Array<{
    id: string
    version: number
    batchNo?: string | null
    isActive?: boolean
    salePrice?: number
    expiryDate?: string | null
    uomPrices?: SalePriceVersionSelection['uomPrices']
  }>
  generalSalePrice?: number | null
  generalUomPrices?: SalePriceVersionSelection['uomPrices']
  /** Product base UOM — the row whose price drives the gross value. */
  baseUomId?: string
}): BatchPricingCard[] {
  const generalPrices = input.salePrices.filter(row => !String(row.batchNo ?? '').trim())
  const generalActive = generalPrices.find(row => row.isActive) ?? generalPrices[0] ?? null
  const generalUomPrices = generalActive?.uomPrices?.length
    ? generalActive.uomPrices.map(uom => ({ ...uom }))
    : (input.generalUomPrices || []).map(uom => ({ ...uom }))
  const cards: BatchPricingCard[] = [{
    key: 'general',
    scope: 'general',
    batchNo: null,
    label: 'General',
    expiryDate: null,
    remainingQty: null,
    unitCost: null,
    lotStatus: null,
    priceId: generalActive ? String(generalActive.id) : null,
    priceVersion: generalActive ? Number(generalActive.version) : null,
    isPriceActive: true,
    salePrice: generalActive != null
      ? Number(generalActive.salePrice ?? 0)
      : (input.generalSalePrice != null ? Number(input.generalSalePrice) : null),
    uomPrices: generalUomPrices,
    unitSalePrice: baseUnitSalePrice(
      generalUomPrices,
      input.baseUomId,
      input.generalSalePrice != null ? Number(input.generalSalePrice) : null,
    ),
    grossValue: null,
  }]

  const generalUnit = cards[0]!.unitSalePrice
  for (const lot of input.lots) {
    const batchNo = String(lot.batchNo || '').trim()
    if (!batchNo) continue
    const scoped = input.salePrices.filter(row => String(row.batchNo ?? '').trim() === batchNo)
    const active = scoped.find(row => row.isActive) ?? null
    const latest = active ?? scoped[0] ?? null
    const uomPrices = latest?.uomPrices?.length ? latest.uomPrices.map(uom => ({ ...uom })) : []
    const remainingQty = lot.remainingQty != null ? Number(lot.remainingQty) : null
    const unitSalePrice = baseUnitSalePrice(
      uomPrices,
      input.baseUomId,
      latest != null ? Number(latest.salePrice ?? 0) : generalUnit,
    )
    cards.push({
      key: `batch:${batchNo}`,
      scope: 'batch',
      batchNo,
      label: batchNo,
      expiryDate: lot.expiryDate ?? latest?.expiryDate ?? null,
      remainingQty,
      unitCost: lot.unitCost != null ? Number(lot.unitCost) : null,
      lotStatus: lot.status ?? null,
      priceId: latest ? String(latest.id) : null,
      priceVersion: latest ? Number(latest.version) : null,
      isPriceActive: active != null,
      salePrice: latest != null ? Number(latest.salePrice ?? 0) : null,
      uomPrices,
      unitSalePrice,
      grossValue: remainingQty != null && unitSalePrice != null
        ? multiplyDecimalSafe(remainingQty, unitSalePrice)
        : null,
    })
  }
  return cards
}
