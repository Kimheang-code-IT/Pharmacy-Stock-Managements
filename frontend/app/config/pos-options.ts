/** Shared Stock & POS option lists (mock-seeded and later served by the API). */
export const PAYMENT_METHODS = ['Cash', 'Card', 'Mobile Payment', 'Bank Transfer', 'Credit'] as const

export const STOCK_OPERATION_TYPES = ['stock_in', 'adjustment', 'damage', 'expiry'] as const

export type StockOperationType = (typeof STOCK_OPERATION_TYPES)[number]

/** Movement-kind filter used by the stock history dialog on the Stock list
 *  (Current Stock is display-only and never opens the dialog). */
export type StockHistoryKind = 'stock_in' | 'stock_out' | 'damage'

export const STOCK_OPERATION_META: Record<StockOperationType, { label: string, icon: string, color: 'success' | 'primary' | 'warning' | 'error' }> = {
  stock_in: { label: 'Stock In', icon: 'i-lucide-package-plus', color: 'success' },
  adjustment: { label: 'Adjustment', icon: 'i-lucide-scale', color: 'primary' },
  damage: { label: 'Damage', icon: 'i-lucide-package-x', color: 'warning' },
  expiry: { label: 'Expiry', icon: 'i-lucide-calendar-x', color: 'error' },
}
