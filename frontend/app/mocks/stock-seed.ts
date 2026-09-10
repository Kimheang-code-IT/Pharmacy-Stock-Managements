import type { AppRecord } from '~/config/admin-seed'
import type { DeliveryStatus } from '~/utils/delivery/notes'
import { createId, dateOnly, daysAgo } from './seed'

/**
 * Deterministic mock catalogue for the Stock & POS vertical slice.
 * Records are plain `AppRecord`s so the generic list/detail/module views and
 * the entity repository can consume them without collection-specific logic.
 */

function pick<T>(items: readonly T[], i: number): T {
  return items[i % items.length]!
}

export const categories: AppRecord[] = [
  { id: 'cat1', code: 'CAT-001', name: 'Soft Drinks', description: 'Bottled and canned beverages.', status: 'Active', productCount: 4, createdAt: daysAgo(120) },
  { id: 'cat2', code: 'CAT-002', name: 'Snacks', description: 'Packaged snacks and biscuits.', status: 'Active', productCount: 3, createdAt: daysAgo(118) },
  { id: 'cat3', code: 'CAT-003', name: 'Household', description: 'Cleaning and household supplies.', status: 'Active', productCount: 3, createdAt: daysAgo(100) },
  { id: 'cat4', code: 'CAT-004', name: 'Personal Care', description: 'Soaps, shampoo and hygiene products.', status: 'Active', productCount: 3, createdAt: daysAgo(96) },
  { id: 'cat5', code: 'CAT-005', name: 'Dairy', description: 'Milk, cheese and chilled products.', status: 'Active', productCount: 3, createdAt: daysAgo(90) },
  { id: 'cat6', code: 'CAT-006', name: 'Stationery', description: 'School and office supplies.', status: 'Inactive', productCount: 1, createdAt: daysAgo(80) },
]

export const uoms: AppRecord[] = [
  { id: 'uom1', code: 'UOM-PCS', name: 'Piece', symbol: 'pcs', description: 'Individual pieces or units.', status: 'Active', createdAt: daysAgo(130) },
  { id: 'uom2', code: 'UOM-BOX', name: 'Box', symbol: 'box', description: 'Boxed quantities.', status: 'Active', createdAt: daysAgo(130) },
  { id: 'uom3', code: 'UOM-CAN', name: 'Can', symbol: 'can', description: 'Canned goods and drinks.', status: 'Active', createdAt: daysAgo(129) },
  { id: 'uom4', code: 'UOM-BTL', name: 'Bottle', symbol: 'btl', description: 'Bottled products.', status: 'Active', createdAt: daysAgo(128) },
  { id: 'uom5', code: 'UOM-KG', name: 'Kilogram', symbol: 'kg', description: 'Weight-based goods.', status: 'Active', createdAt: daysAgo(127) },
  { id: 'uom6', code: 'UOM-PACK', name: 'Pack', symbol: 'pack', description: 'Packed or bagged goods.', status: 'Inactive', createdAt: daysAgo(126) },
]

export const uomById = (id: string) => uoms.find(uom => uom.id === id)

export const brands: AppRecord[] = [
  { id: 'br1', code: 'BR-001', name: 'Coca-Cola', description: 'Global beverage brand.', status: 'Active', productCount: 2, createdAt: daysAgo(110) },
  { id: 'br2', code: 'BR-002', name: 'Mama', description: 'Instant noodles and snacks.', status: 'Active', productCount: 1, createdAt: daysAgo(108) },
  { id: 'br3', code: 'BR-003', name: 'Sunlight', description: 'Household cleaning products.', status: 'Active', productCount: 1, createdAt: daysAgo(105) },
  { id: 'br4', code: 'BR-004', name: 'Lifebuoy', description: 'Personal care and hygiene.', status: 'Active', productCount: 1, createdAt: daysAgo(99) },
  { id: 'br5', code: 'BR-005', name: 'Mead Johnson', description: 'Dairy and nutrition products.', status: 'Active', productCount: 1, createdAt: daysAgo(95) },
  { id: 'br6', code: 'BR-006', name: 'Pilot', description: 'Stationery and writing supplies.', status: 'Inactive', productCount: 1, createdAt: daysAgo(85) },
]

export const brandById = (id: string) => brands.find(brand => brand.id === id)

export const suppliers: AppRecord[] = [
  { id: 'sup1', code: 'SUP-0001', name: 'Angkor Wholesale Co.', phone: '012 345 678', location: 'Phnom Penh, St. 271', address: 'Phnom Penh, St. 271', status: 'Active', totalDebt: 1850, createdAt: daysAgo(200) },
  { id: 'sup2', code: 'SUP-0002', name: 'Mekong Trading', phone: '097 456 789', location: 'Phnom Penh, St. 128', address: 'Phnom Penh, St. 128', status: 'Active', totalDebt: 0, createdAt: daysAgo(190) },
  { id: 'sup3', code: 'SUP-0003', name: 'Tonle Consumer Goods', phone: '086 111 222', location: 'Siem Reap, National Rd 6', address: 'Siem Reap, National Rd 6', status: 'Active', totalDebt: 640, createdAt: daysAgo(150) },
  { id: 'sup4', code: 'SUP-0004', name: 'Bassac Foods Import', phone: '011 999 888', location: 'Phnom Penh, Chbar Ampov', address: 'Phnom Penh, Chbar Ampov', status: 'Inactive', totalDebt: 0, createdAt: daysAgo(140) },
]

export const customers: AppRecord[] = [
  { id: 'cus1', code: 'CUS-0001', name: 'Nita Sok', phone: '012 777 001', location: 'Phnom Penh, Toul Kork', address: 'Phnom Penh, Toul Kork', status: 'Active', debtBalance: 246, createdAt: daysAgo(180) },
  { id: 'cus2', code: 'CUS-0002', name: 'Ratana Pich', phone: '012 777 002', location: 'Phnom Penh, Chamkarmon', address: 'Phnom Penh, Chamkarmon', status: 'Active', debtBalance: 0, createdAt: daysAgo(178) },
  { id: 'cus3', code: 'CUS-0003', name: 'Vuthy Long', phone: '012 777 003', location: 'Kandal, Ta Khmau', address: 'Kandal, Ta Khmau', status: 'Active', debtBalance: 125, createdAt: daysAgo(150) },
  { id: 'cus4', code: 'CUS-0004', name: 'Sopheak Nguon', phone: '012 777 004', location: 'Phnom Penh, Sen Sok', address: 'Phnom Penh, Sen Sok', status: 'Active', debtBalance: 0, createdAt: daysAgo(120) },
  { id: 'cus5', code: 'CUS-0005', name: 'Bopha Chen', phone: '012 777 005', location: 'Phnom Penh, Russey Keo', address: 'Phnom Penh, Russey Keo', status: 'Active', debtBalance: 68.5, createdAt: daysAgo(90) },
  { id: 'cus6', code: 'CUS-0006', name: 'Chanlina Tep', phone: '012 777 006', location: 'Phnom Penh, Dangkor', address: 'Phnom Penh, Dangkor', status: 'Inactive', debtBalance: 0, createdAt: daysAgo(70) },
]

type ProductSeed = {
  name: string
  categoryId: string
  uomId: string
  cost: number
  price: number
  qty: number
  barcode: string
  brandId?: string
  /** When set, product tracks expiry and list shows this nearest lot date. */
  expiryDate?: string
}

/**
 * Pricing rows for a few seeded products (spec §2.1.3: the Pricing tab edits
 * these `uomConversions`; all other products materialize a single base=base
 * row). Each product's full row list is persisted: the base=base row plus
 * pack rows. Exactly one row per product has `isDefaultSale` — the UOM the
 * POS pre-selects on add-to-cart. 1 box of Coca-Cola = 12 cans at $9.60; the
 * can price ($0.80) stays the base-row price.
 */
function pricingRow(uomId: string, symbol: string, baseUomId: string, baseSymbol: string, factor: number, costPrice: number | null, salePrice: number, isDefaultSale: boolean) {
  return {
    uomId,
    uomSymbol: symbol,
    convertUomId: baseUomId,
    convertUomSymbol: baseSymbol,
    factorToBase: factor,
    costPrice,
    salePrice,
    isDefaultSale,
  }
}

const UOM_CONVERSIONS_BY_PRODUCT: Record<string, Array<Record<string, unknown>>> = {
  prd1: [
    pricingRow('uom3', 'can', 'uom3', 'can', 1, 0.5, 0.8, true),
    pricingRow('uom2', 'box', 'uom3', 'can', 12, 6, 9.6, false),
  ],
  prd3: [
    pricingRow('uom4', 'btl', 'uom4', 'btl', 1, 0.3, 0.6, true),
    pricingRow('uom2', 'box', 'uom4', 'btl', 6, null, 3.6, false),
  ],
  prd17: [
    pricingRow('uom1', 'pcs', 'uom1', 'pcs', 1, 0.2, 0.4, true),
    pricingRow('uom2', 'box', 'uom1', 'pcs', 50, null, 20, false),
  ],
}

const productSeeds: ProductSeed[] = [
  { name: 'Coca-Cola 350ml', categoryId: 'cat1', uomId: 'uom3', cost: 0.5, price: 0.8, qty: 240, barcode: '8801001234501', brandId: 'br1', expiryDate: '2027-03-15' },
  { name: 'Sprite 350ml', categoryId: 'cat1', uomId: 'uom3', cost: 0.5, price: 0.8, qty: 180, barcode: '8801001234502', brandId: 'br1', expiryDate: '2027-02-28' },
  { name: 'Water 1.5L', categoryId: 'cat1', uomId: 'uom4', cost: 0.3, price: 0.6, qty: 500, barcode: '8801001234503', expiryDate: '2028-01-10' },
  { name: 'Energy Drink 250ml', categoryId: 'cat1', uomId: 'uom3', cost: 0.9, price: 1.5, qty: 96, barcode: '8801001234504', expiryDate: '2026-11-30' },
  { name: 'Instant Noodles 60g', categoryId: 'cat2', uomId: 'uom1', cost: 0.45, price: 0.75, qty: 320, barcode: '8801001234505', brandId: 'br2', expiryDate: '2026-12-20' },
  { name: 'Salted Chips 90g', categoryId: 'cat2', uomId: 'uom1', cost: 0.7, price: 1.2, qty: 140, barcode: '8801001234506', expiryDate: '2026-10-05' },
  { name: 'Butter Cookies 200g', categoryId: 'cat2', uomId: 'uom2', cost: 1.1, price: 1.8, qty: 60, barcode: '8801001234507', expiryDate: '2026-09-18' },
  { name: 'Dish Soap 500ml', categoryId: 'cat3', uomId: 'uom4', cost: 1.2, price: 2.0, qty: 80, barcode: '8801001234508', brandId: 'br3' },
  { name: 'Laundry Powder 1kg', categoryId: 'cat3', uomId: 'uom5', cost: 2.4, price: 3.5, qty: 55, barcode: '8801001234509' },
  { name: 'Trash Bags 20pcs', categoryId: 'cat3', uomId: 'uom2', cost: 0.9, price: 1.4, qty: 110, barcode: '8801001234510' },
  { name: 'Soap Bar 120g', categoryId: 'cat4', uomId: 'uom1', cost: 0.55, price: 0.95, qty: 200, barcode: '8801001234511', brandId: 'br4', expiryDate: '2027-06-01' },
  { name: 'Shampoo 400ml', categoryId: 'cat4', uomId: 'uom4', cost: 1.8, price: 2.9, qty: 72, barcode: '8801001234512', expiryDate: '2027-08-15' },
  { name: 'Toothpaste 150g', categoryId: 'cat4', uomId: 'uom1', cost: 1.0, price: 1.7, qty: 130, barcode: '8801001234513', expiryDate: '2027-04-22' },
  { name: 'Fresh Milk 1L', categoryId: 'cat5', uomId: 'uom4', cost: 1.3, price: 1.9, qty: 40, barcode: '8801001234514', brandId: 'br5', expiryDate: '2026-09-12' },
  { name: 'Yogurt Cup 100g', categoryId: 'cat5', uomId: 'uom1', cost: 0.5, price: 0.9, qty: 8, barcode: '8801001234515', expiryDate: '2026-09-08' },
  { name: 'Cheese Slices 10pcs', categoryId: 'cat5', uomId: 'uom2', cost: 1.5, price: 2.4, qty: 25, barcode: '8801001234516', expiryDate: '2026-09-25' },
  { name: 'Ballpoint Pen', categoryId: 'cat6', uomId: 'uom1', cost: 0.2, price: 0.4, qty: 400, barcode: '8801001234517', brandId: 'br6' },
]

export const products: AppRecord[] = productSeeds.map((seed, i) => {
  const category = categories.find(item => item.id === seed.categoryId)!
  const uom = uomById(seed.uomId)!
  const brand = seed.brandId ? brandById(seed.brandId) : undefined
  const id = `prd${i + 1}`
  return {
    id,
    code: `PRD-${String(i + 1).padStart(4, '0')}`,
    name: seed.name,
    categoryId: seed.categoryId,
    category: category.name,
    brandId: brand?.id ?? null,
    brand: brand?.name ?? '',
    supplierId: `sup${(i % 3) + 1}`,
    supplier: suppliers[i % 3]!.name,
    barcode: seed.barcode,
    uomId: uom.id,
    uom: uom.name,
    uomSymbol: uom.symbol,
    costPrice: seed.cost,
    salePrice: seed.price,
    quantity: seed.qty,
    // Full Pricing rows (spec §2.1.3, edited on the product Pricing tab).
    // Stock stays in the base UOM; products without pack rows still sell in
    // their base UOM (the UI materializes a base=base row on save).
    uomConversions: UOM_CONVERSIONS_BY_PRODUCT[id] ?? [],
    expiryTracking: Boolean(seed.expiryDate),
    // FIFO costing option (off by default — weighted average cost).
    fifo: false,
    // Nearest lot expiry for the Stock list column (blank when not tracked).
    expiryDate: seed.expiryDate ?? null,
    // Most products have an image; leave a few null so the placeholder path stays verifiable.
    imageUrl: i % 8 === 7 ? null : `https://picsum.photos/seed/${id}/480/360`,
    status: seed.qty <= 10 ? 'Low Stock' : 'Active',
    createdAt: daysAgo(85 - i),
  }
})

export const productName = (id: string) => String(products.find(p => p.id === id)?.name || 'Unknown product')
export const productById = (id: string) => products.find(p => p.id === id)

/**
 * Sale-price versions (spec: product_sale_prices). Exactly one POS-active
 * version per product and the active price always equals `product.salePrice`,
 * so the Stock list and POS stay in sync.
 *
 * Base seed: version 1 = current sale price, active, dated at product creation.
 * Every 4th product also has 1–2 older versions (a price change since
 * creation): version 1 starts at the original price and the newest version
 * carries the current price as the active one.
 */
export const productSalePrices: AppRecord[] = products.flatMap((product, i) => {
  const price = Number(product.salePrice)
  const createdAt = String(product.createdAt)
  const createdDay = createdAt.slice(0, 10)
  const base = {
    productId: String(product.id),
    product: String(product.name),
    createdAt,
  }
  if (i % 4 === 1) {
    // Price was raised since creation: keep older, cheaper versions.
    const original = Math.max(0.05, Math.round((price - 0.1) * 100) / 100)
    return [
      { ...base, id: `psp${i + 1}v1`, salePrice: original, date: createdDay, isActive: false, version: 1 },
      ...(i % 8 === 1
        ? [{ ...base, id: `psp${i + 1}v2`, salePrice: Math.max(0.05, Math.round((price - 0.05) * 100) / 100), date: dateOnly(85 - i - 5), isActive: false, version: 2 }]
        : []),
      { ...base, id: `psp${i + 1}v3`, salePrice: price, date: dateOnly(85 - i - 20), isActive: true, version: i % 8 === 1 ? 3 : 2 },
    ]
  }
  return [{ ...base, id: `psp${i + 1}v1`, salePrice: price, date: createdDay, isActive: true, version: 1 }]
})

/* ------------------------------------------------------------------ */
/* Transactions                                                        */
/* ------------------------------------------------------------------ */

const PAYMENT_METHODS = ['Cash', 'Card', 'Mobile Payment'] as const

function saleItems(seedIndex: number, lineCount: number): AppRecord[] {
  return Array.from({ length: lineCount }, (_, i) => {
    const product = pick(products, seedIndex + i * 3)
    const quantity = ((seedIndex + i) % 4) + 1
    const price = Number(product.salePrice)
    return {
      id: createId('line'),
      productId: String(product.id),
      name: String(product.name),
      quantity,
      price,
      total: Math.round(price * quantity * 100) / 100,
    }
  })
}

function buildSales(): AppRecord[] {
  const rows: AppRecord[] = []
  let counter = 1001
  for (let day = 29; day >= 0; day -= 1) {
    const salesPerDay = day % 4 === 0 ? 1 : day % 3 === 0 ? 2 : 3
    for (let s = 0; s < salesPerDay; s += 1) {
      const seedIndex = day * 3 + s
      const items = saleItems(seedIndex, ((seedIndex % 3) + 1) + 1)
      const subtotal = Math.round(items.reduce((sum, item) => sum + Number(item.total), 0) * 100) / 100
      const discount = seedIndex % 7 === 0 ? Math.round(subtotal * 0.05 * 100) / 100 : 0
      const total = Math.round((subtotal - discount) * 100) / 100
      const customer = pick(customers, seedIndex)
      const onCredit = seedIndex % 6 === 0 && customer.status === 'Active'
      const paidAmount = onCredit ? Math.round(total * 0.5 * 100) / 100 : total
      const status = paidAmount >= total ? 'Paid' : paidAmount > 0 ? 'Partial' : 'Unpaid'
      rows.push({
        id: `sale${counter - 1000}`,
        saleNo: `SALE-${String(counter).padStart(5, '0')}`,
        createdAt: daysAgo(day),
        date: dateOnly(day),
        customerId: customer.id,
        customer: customer.name,
        items,
        lineCount: items.length,
        subtotal,
        discount,
        total,
        paidAmount,
        remaining: Math.round((total - paidAmount) * 100) / 100,
        paymentMethod: onCredit ? 'Credit' : pick(PAYMENT_METHODS, seedIndex),
        cashier: pick(['Sokha Chan', 'Dara Kim'], seedIndex),
        status,
      })
      counter += 1
    }
  }
  return rows
}

export const sales: AppRecord[] = buildSales()

/** Customer-return history rows (sale_returns documents, spec SRT-…). */
export const saleReturns: AppRecord[] = sales.slice(0, 4).map((sale, i) => {
  const items = (sale.items as AppRecord[]).slice(0, 1)
  const refund = Math.round(items.reduce((sum, item) => sum + Number(item.total), 0) * 0.5 * 100) / 100
  return {
    id: `srt${i + 1}`,
    returnNo: `SRT-${String(13 - i).padStart(6, '0')}`,
    saleId: String(sale.id),
    saleNo: String(sale.saleNo),
    createdAt: daysAgo(i * 4 + 1),
    date: dateOnly(i * 4 + 1),
    customer: String(sale.customer || ''),
    itemCount: items.length,
    refundAmount: refund,
    restockedQuantity: i % 2 === 0 ? 1 : 0,
    reason: pick(['Wrong item ordered', 'Damaged on delivery', 'Customer changed mind', 'Expired product'], i),
    user: String(sale.cashier || '—'),
  }
})

export const stockIns: AppRecord[] = Array.from({ length: 14 }, (_, i) => {
  const supplier = suppliers[i % 3]!
  const items: AppRecord[] = saleItems(i * 5 + 2, ((i % 2) + 1) + 1).map(item => ({
    ...item,
    price: Number(productById(String(item.productId))?.costPrice ?? item.price),
  }))
  const total = Math.round(items.reduce((sum, item) => sum + Number(item.price) * Number(item.quantity), 0) * 100) / 100
  const unpaid = i % 4 === 1
  const paidAmount = unpaid ? Math.round(total * 0.4 * 100) / 100 : total
  return {
    id: `sin${i + 1}`,
    purchaseNo: `PIN-${String(80 + i).padStart(5, '0')}`,
    createdAt: daysAgo(28 - i * 2),
    date: dateOnly(28 - i * 2),
    supplierId: supplier.id,
    supplier: supplier.name,
    items,
    lineCount: items.length,
    total,
    paidAmount,
    remaining: Math.round((total - paidAmount) * 100) / 100,
    status: unpaid ? 'Partial' : 'Completed',
    user: pick(['Sokha Chan', 'Dara Kim'], i),
  }
})

/** Supplier-return history rows (purchase_returns documents, spec PRT-…). */
export const purchaseReturns: AppRecord[] = stockIns.slice(0, 3).map((purchase, i) => {
  const items = (purchase.items as AppRecord[]).slice(0, 1)
  const refund = Math.round(items.reduce((sum, item) => sum + Number(item.price) * 1, 0) * 100) / 100
  return {
    id: `prt${i + 1}`,
    returnNo: `PRT-${String(16 - i).padStart(6, '0')}`,
    stockInId: String(purchase.id),
    purchaseNo: String(purchase.purchaseNo),
    createdAt: daysAgo(i * 5 + 2),
    date: dateOnly(i * 5 + 2),
    supplier: String(purchase.supplier || ''),
    itemCount: items.length,
    refundAmount: refund,
    debtReduction: Number(purchase.remaining) > 0 ? refund : 0,
    creditAmount: Number(purchase.remaining) > 0 ? 0 : refund,
    reason: pick(['Damaged in transit', 'Wrong specification', 'Near expiry stock'], i),
    user: String(purchase.user || '—'),
  }
})

export const stockMovements: AppRecord[] = [
  ...sales.flatMap(sale => (sale.items as AppRecord[]).map((item, i) => ({
    id: createId('mv'),
    createdAt: sale.createdAt,
    date: sale.date,
    productId: item.productId,
    product: item.name,
    type: 'Sale',
    quantity: -Number(item.quantity),
    unitPrice: Number(item.price ?? 0),
    unit: String(productById(String(item.productId))?.uomSymbol || ''),
    reference: String(sale.saleNo),
    user: String(sale.cashier || '—'),
    note: i === 0 ? 'POS sale' : '',
  }))),
  ...stockIns.flatMap(purchase => (purchase.items as AppRecord[]).map(item => ({
    id: createId('mv'),
    createdAt: purchase.createdAt,
    date: purchase.date,
    productId: item.productId,
    product: item.name,
    type: 'Stock In',
    quantity: Number(item.quantity),
    unitPrice: Number(item.price ?? 0),
    unit: String(productById(String(item.productId))?.uomSymbol || ''),
    reference: String(purchase.purchaseNo),
    user: String(purchase.user || '—'),
    note: '',
  }))),
  {
    id: 'mv_adj1', createdAt: daysAgo(2), date: dateOnly(2), productId: 'prd15', product: 'Yogurt Cup 100g',
    type: 'Damage', quantity: -6, reference: 'ADJ-00015', user: 'Dara Kim', note: 'Broken during transport',
  },
  {
    id: 'mv_adj2', createdAt: daysAgo(5), date: dateOnly(5), productId: 'prd14', product: 'Fresh Milk 1L',
    type: 'Expiry', quantity: -10, reference: 'ADJ-00014', user: 'Sokha Chan', note: 'Expired stock removal',
  },
  {
    id: 'mv_adj3', createdAt: daysAgo(9), date: dateOnly(9), productId: 'prd1', product: 'Coca-Cola 350ml',
    type: 'Adjustment', quantity: 4, reference: 'ADJ-00013', user: 'Dara Kim', note: 'Stock count correction',
  },
].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)))

/* ------------------------------------------------------------------ */
/* Delivery notes (fulfillment of sold products — no stock impact)     */
/* ------------------------------------------------------------------ */

interface DeliveryNoteSeed {
  status: DeliveryStatus
  /** Sale picked as Nth from the end of the seeded sales (0 = newest). */
  saleFromEnd: number
  /** [sale item index, qty to deliver] pairs. */
  lines: Array<[number, number]>
  scheduledInDays: number
  driverName?: string
  vehicleNote?: string
  note?: string
  cancelReason?: string
  createdDaysAgo: number
}

const deliveryNoteSeeds: DeliveryNoteSeed[] = [
  { status: 'Delivered', saleFromEnd: 5, lines: [[0, 2]], scheduledInDays: -3, driverName: 'Vannak Ouk', vehicleNote: 'Moto 1AB-1234', createdDaysAgo: 5 },
  { status: 'Cancelled', saleFromEnd: 4, lines: [[0, 1]], scheduledInDays: -1, note: 'Customer picked up at the shop instead.', cancelReason: 'Customer cancelled the delivery request.', createdDaysAgo: 4 },
  { status: 'Confirmed', saleFromEnd: 3, lines: [[0, 1]], scheduledInDays: 1, driverName: 'Vannak Ouk', createdDaysAgo: 2 },
  { status: 'Out for Delivery', saleFromEnd: 2, lines: [[0, 3]], scheduledInDays: 0, driverName: 'Dara Kim', vehicleNote: 'Tuk-tuk 2CD-5678', createdDaysAgo: 2 },
  { status: 'Delivered', saleFromEnd: 1, lines: [[1, 1]], scheduledInDays: -1, driverName: 'Vannak Ouk', createdDaysAgo: 2 },
  { status: 'Draft', saleFromEnd: 0, lines: [[0, 1]], scheduledInDays: 2, note: 'Call customer before dispatch.', createdDaysAgo: 1 },
  { status: 'Confirmed', saleFromEnd: 1, lines: [[0, 2]], scheduledInDays: 3, driverName: 'Sreymom Lim', note: 'Second trip for the remaining boxes.', createdDaysAgo: 1 },
]

function buildDeliveryNotes(): AppRecord[] {
  const rows: AppRecord[] = []
  deliveryNoteSeeds.forEach((seed, i) => {
    const sale = sales[sales.length - 1 - seed.saleFromEnd]!
    const items = Array.isArray(sale.items) ? sale.items as AppRecord[] : []
    const customer = customers.find(row => row.id === sale.customerId)
    const lines = seed.lines
      .map(([itemIndex, qty]): AppRecord | null => {
        const item = items[itemIndex]
        if (!item) return null
        const product = productById(String(item.productId))
        return {
          id: createId('dline'),
          saleItemId: String(item.id),
          productId: String(item.productId),
          product: String(item.name),
          uomSymbol: String(product?.uomSymbol || ''),
          qtyOrdered: Number(item.quantity || 0),
          qtyToDeliver: qty,
          qtyDelivered: seed.status === 'Delivered' ? qty : 0,
        }
      })
      .filter((line): line is AppRecord => Boolean(line))
    if (!lines.length) return
    const delivered = seed.status === 'Delivered'
    rows.push({
      id: `dn${i + 1}`,
      deliveryNo: `DN-${String(i + 1).padStart(6, '0')}`,
      saleId: String(sale.id),
      saleNo: String(sale.saleNo),
      invoiceNo: String(sale.invoiceNo || sale.saleNo),
      customerId: sale.customerId ? String(sale.customerId) : null,
      customer: String(sale.customer || 'Walk-in customer'),
      deliveryName: customer?.name ? String(customer.name) : String(sale.customer || 'Walk-in customer'),
      deliveryPhone: customer?.phone ? String(customer.phone) : '—',
      deliveryAddress: customer?.address ? String(customer.address) : '',
      scheduledDate: dateOnly(seed.scheduledInDays),
      deliveredAt: delivered ? daysAgo(Math.max(0, -seed.scheduledInDays)) : null,
      status: seed.status,
      driverName: seed.driverName ?? null,
      vehicleNote: seed.vehicleNote ?? null,
      note: seed.note ?? null,
      cancelReason: seed.cancelReason ?? null,
      items: lines,
      itemCount: lines.length,
      createdBy: 'Sokha Chan',
      createdAt: daysAgo(seed.createdDaysAgo),
      updatedAt: daysAgo(Math.max(0, seed.createdDaysAgo - 1)),
    })
  })
  return rows
}

export const deliveryNotes: AppRecord[] = buildDeliveryNotes()

export const customerDebtPayments: AppRecord[] = [
  { id: 'cdp1', createdAt: daysAgo(1), date: dateOnly(1), customerId: 'cus1', customer: 'Nita Sok', amount: 120, paymentMethod: 'Cash', reference: 'PAY-00310', user: 'Dara Kim' },
  { id: 'cdp2', createdAt: daysAgo(4), date: dateOnly(4), customerId: 'cus3', customer: 'Vuthy Long', amount: 75, paymentMethod: 'Mobile Payment', reference: 'PAY-00309', user: 'Dara Kim' },
  { id: 'cdp3', createdAt: daysAgo(8), date: dateOnly(8), customerId: 'cus5', customer: 'Bopha Chen', amount: 30, paymentMethod: 'Cash', reference: 'PAY-00308', user: 'Sokha Chan' },
]

export const supplierDebtPayments: AppRecord[] = [
  { id: 'sdp1', createdAt: daysAgo(2), date: dateOnly(2), supplierId: 'sup3', supplier: 'Tonle Consumer Goods', amount: 360, paymentMethod: 'Bank Transfer', reference: 'PAY-00311', user: 'Sokha Chan' },
  { id: 'sdp2', createdAt: daysAgo(6), date: dateOnly(6), supplierId: 'sup1', supplier: 'Angkor Wholesale Co.', amount: 900, paymentMethod: 'Bank Transfer', reference: 'PAY-00307', user: 'Sokha Chan' },
]

/* ------------------------------------------------------------------ */
/* Invoice/document-level debt rows (spec §2.1.10 debt reports).       */
/* One row per customer debt invoice / supplier purchase debt document.*/
/* ------------------------------------------------------------------ */

const DEBT_TERM_DAYS = 30

function plusDays(day: string, days: number) {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

function debtStatus(total: unknown, paid: unknown) {
  const remaining = Math.round((Number(total || 0) - Number(paid || 0)) * 100) / 100
  if (remaining <= 0) return 'PAID'
  return Number(paid || 0) > 0 ? 'PARTIAL' : 'UNPAID'
}

function buildCustomerDebts(): AppRecord[] {
  return sales
    .filter(sale => Number(sale.remaining) > 0 || sale.paymentMethod === 'Credit')
    .map((sale, index) => ({
      id: `cdebt${index + 1}`,
      createdAt: String(sale.createdAt),
      saleId: String(sale.id),
      customerId: String(sale.customerId),
      customer: String(sale.customer || 'Walk-in customer'),
      invoiceNo: String(sale.invoiceNo || sale.saleNo),
      date: String(sale.date),
      invoiceTotal: Number(sale.total),
      paidAmount: Number(sale.paidAmount),
      remainingAmount: Number(sale.remaining),
      dueDate: plusDays(String(sale.date), DEBT_TERM_DAYS),
      status: debtStatus(sale.total, sale.paidAmount),
    }))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
}

function buildSupplierDebts(): AppRecord[] {
  return stockIns
    .filter(row => Number(row.remaining) > 0)
    .map((row, index) => ({
      id: `sdebt${index + 1}`,
      createdAt: String(row.createdAt),
      stockTransactionId: String(row.id),
      supplierId: String(row.supplierId),
      supplier: String(row.supplier || '—'),
      purchaseNo: String(row.purchaseNo),
      date: String(row.date),
      totalAmount: Number(row.total),
      paidAmount: Number(row.paidAmount),
      remainingAmount: Number(row.remaining),
      dueDate: plusDays(String(row.date), DEBT_TERM_DAYS),
      status: debtStatus(row.total, row.paidAmount),
    }))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
}

export const customerDebts: AppRecord[] = buildCustomerDebts()
export const supplierDebts: AppRecord[] = buildSupplierDebts()

export const expenses: AppRecord[] = [
  { id: 'exp1', createdAt: daysAgo(1), date: dateOnly(1), category: 'Utilities', description: 'Electricity bill', amount: 85, paymentMethod: 'Cash', user: 'Sokha Chan' },
  { id: 'exp2', createdAt: daysAgo(3), date: dateOnly(3), category: 'Rent', description: 'Shop rent (weekly)', amount: 150, paymentMethod: 'Bank Transfer', user: 'Sokha Chan' },
  { id: 'exp3', createdAt: daysAgo(5), date: dateOnly(5), category: 'Salaries', description: 'Staff weekly pay', amount: 350, paymentMethod: 'Cash', user: 'Sokha Chan' },
  { id: 'exp4', createdAt: daysAgo(9), date: dateOnly(9), category: 'Supplies', description: 'POS paper rolls', amount: 18, paymentMethod: 'Cash', user: 'Dara Kim' },
  { id: 'exp5', createdAt: daysAgo(12), date: dateOnly(12), category: 'Utilities', description: 'Water bill', amount: 12.5, paymentMethod: 'Cash', user: 'Dara Kim' },
  { id: 'exp6', createdAt: daysAgo(15), date: dateOnly(15), category: 'Rent', description: 'Shop rent (weekly)', amount: 150, paymentMethod: 'Bank Transfer', user: 'Sokha Chan' },
  { id: 'exp7', createdAt: daysAgo(19), date: dateOnly(19), category: 'Transport', description: 'Delivery motorbike fuel', amount: 22, paymentMethod: 'Cash', user: 'Dara Kim' },
  { id: 'exp8', createdAt: daysAgo(23), date: dateOnly(23), category: 'Salaries', description: 'Staff weekly pay', amount: 350, paymentMethod: 'Cash', user: 'Sokha Chan' },
]