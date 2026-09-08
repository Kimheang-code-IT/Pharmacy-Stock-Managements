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
  /** Exactly one row per product is the POS default sale. */
  isDefaultSale: boolean
  /** Cost per this UOM; `null` = derived from base cost × factor on save. */
  costPrice: number | null
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
  return rows.find(row => row.isDefaultSale)
    || rows.find(row => row.uomId === String(product?.uomId ?? ''))
    || rows[0]!
}

/** Unit price for a UOM: the Pricing row's sale price, else the base sale price. */
export function salePriceForUom(product: Record<string, unknown> | null | undefined, uomId: string): number | null {
  if (!product) return null
  const conversion = conversionForUom(product, uomId)
  if (conversion) return conversion.salePrice
  if (String(product.uomId ?? '') === String(uomId)) return Number(product.salePrice ?? 0)
  return null
}
