export const ApiEndpoints = {
  AUTH_LOGIN: '/api/v1/auth/login',
  AUTH_LOGOUT: '/api/v1/auth/logout',
  AUTH_ME: '/api/v1/auth/me',
  AUTH_REFRESH: '/api/v1/auth/refresh',
  AUTH_FORGOT_PASSWORD: '/api/v1/auth/forgot-password',
  AUTH_RESET_VERIFY: '/api/v1/auth/forgot-password/verify',
  AUTH_RESET_RESEND: '/api/v1/auth/forgot-password/resend',
  AUTH_RESET_PASSWORD: '/api/v1/auth/forgot-password/reset',
  AUTH_RESET_HANDOFF: '/api/v1/auth/forgot-password/handoff',
  AUTH_CHANGE_PASSWORD: '/api/v1/auth/change-password',
  AUTH_PROFILE_AVATAR: '/api/v1/auth/profile/avatar',
  AUTH_TELEGRAM_LINK_CODE: '/api/v1/auth/telegram/link-code',

  CATEGORIES: '/api/v1/categories',
  CATEGORY: (id: string) => `/api/v1/categories/${id}`,

  UOMS: '/api/v1/uoms',
  UOM: (id: string) => `/api/v1/uoms/${id}`,

  BRANDS: '/api/v1/brands',
  BRAND: (id: string) => `/api/v1/brands/${id}`,

  PRODUCTS: '/api/v1/products',
  PRODUCT: (id: string) => `/api/v1/products/${id}`,

  SUPPLIERS: '/api/v1/suppliers',
  SUPPLIER: (id: string) => `/api/v1/suppliers/${id}`,
  SUPPLIER_PAYMENTS: (id: string) => `/api/v1/suppliers/${id}/payments`,
  /** Spec §7: POST /suppliers/{id}/debts/{debt_id}/payments. */
  SUPPLIER_DEBT_PAYMENTS: (supplierId: string, debtId: string) =>
    `/api/v1/suppliers/${supplierId}/debts/${debtId}/payments`,

  CUSTOMERS: '/api/v1/customers',
  CUSTOMER: (id: string) => `/api/v1/customers/${id}`,
  CUSTOMER_PAYMENTS: (id: string) => `/api/v1/customers/${id}/payments`,
  /** Spec §7: POST /customers/{id}/debts/{debt_id}/payments. */
  CUSTOMER_DEBT_PAYMENTS: (customerId: string, debtId: string) =>
    `/api/v1/customers/${customerId}/debts/${debtId}/payments`,

  SALES: '/api/v1/pos/sales',
  /** Spec §7 POS: checkout posts to POST /pos/sales (same canonical path as SALES). */
  POS_SALE_COMPLETE: '/api/v1/pos/sales',
  SALE_RETURN: (id: string) => `/api/v1/pos/sales/${id}/return`,
  POS_RECEIPT: (id: string) => `/api/v1/pos/sales/${id}/receipt`,
  POS_PRODUCT_SEARCH: '/api/v1/pos/products/search',
  POS_PRODUCT_BARCODE: (barcode: string) => `/api/v1/pos/products/barcode/${encodeURIComponent(barcode)}`,
  POS_PRODUCT_DELIVERY_NOTE: (saleId: string) => `/api/v1/pos/sales/${saleId}/delivery-notes`,
  /** Stock Out dialog click-through: invoice detail behind one SALE movement. */
  MOVEMENT_INVOICE: (movementId: string) => `/api/v1/stock/movements/${movementId}/invoice`,

  /** Spec §7 Reports: Sales/Purchase reports back the report pages AND the
   *  Return dialogs (rows carry document ids + returnable quantities). */
  REPORT_SALES: '/api/v1/reports/sales',
  REPORT_PURCHASES: '/api/v1/reports/purchases',
  REPORT_SALE_RETURNS: '/api/v1/reports/sale-returns',
  REPORT_PURCHASE_RETURNS: '/api/v1/reports/purchase-returns',

  DELIVERY_NOTES: '/api/v1/delivery-notes',
  DELIVERY_NOTE: (id: string) => `/api/v1/delivery-notes/${id}`,
  DELIVERY_NOTE_STATUS: (id: string) => `/api/v1/delivery-notes/${id}/status`,
  DELIVERY_NOTE_DELIVERABLE_INVOICES: '/api/v1/delivery-notes/deliverable-invoices',

  /** Spec §7 Stock: one create path per operation — never a generic /stock/operations. */
  STOCK_IN: '/api/v1/stock/in',
  STOCK_IN_RETURN: (id: string) => `/api/v1/stock/in/${id}/return`,
  STOCK_ADJUST: '/api/v1/stock/adjust',
  STOCK_DAMAGE: '/api/v1/stock/damage',
  STOCK_EXPIRE: '/api/v1/stock/expire',
  STOCK_MOVEMENTS: '/api/v1/stock/movements',
  /** Product-scoped movement history (spec: GET /stock/products/{id}/history). */
  PRODUCT_HISTORY: (id: string) => `/api/v1/stock/products/${id}/history`,
  /** Stock In cost lots for one product (spec: GET /stock/products/{id}/cost-history). */
  PRODUCT_COST_HISTORY: (id: string) => `/api/v1/stock/products/${id}/cost-history`,
  /** Nested sale-price versions of one product (spec: /products/{id}/sale-prices). */
  PRODUCT_SALE_PRICES: (productId: string) => `/api/v1/products/${productId}/sale-prices`,
  PRODUCT_SALE_PRICE_ACTIVATE: (productId: string, priceId: string) =>
    `/api/v1/products/${productId}/sale-prices/${priceId}/activate`,

  DASHBOARD: '/api/v1/dashboard/summary',
  /** Canonical Finance summary (spec §7 Reports). */
  FINANCE: '/api/v1/reports/finance',
  /** Legacy alias kept for backends that still expose /summary — tried on 404. */
  FINANCE_SUMMARY: '/api/v1/reports/finance/summary',

  CUSTOMER_DEBTS: '/api/v1/reports/customer-debts',
  SUPPLIER_DEBTS: '/api/v1/reports/supplier-debts',
  FINANCE_ENTRIES: '/api/v1/reports/finance/entries',
  FINANCE_EXPENSES: '/api/v1/reports/finance/expenses',

  USERS: '/api/v1/admin/users',
  USER: (id: string) => `/api/v1/admin/users/${id}`,

  ROLES: '/api/v1/admin/roles',
  ROLE: (id: string) => `/api/v1/admin/roles/${id}`,
  ROLE_OPTIONS: '/api/v1/admin/roles/options',
  PERMISSIONS: '/api/v1/admin/permissions',

  AUDIT_LOGS: '/api/v1/admin/audit-logs',

  DOCUMENT_SEQUENCES: '/api/v1/admin/document-sequences',
  DOCUMENT_SEQUENCE: (id: string) => `/api/v1/admin/document-sequences/${id}`,

  EXPORTS: '/api/v1/exports',
  EXPORT: (id: string) => `/api/v1/exports/${id}`,
  EXPORT_DOWNLOAD: (id: string) => `/api/v1/exports/${id}/download`,
  TASK: (taskId: string) => `/api/v1/tasks/${taskId}`,

  APP_INFO: '/api/v1/settings/app-info',
  APP_INFO_RESET: '/api/v1/settings/app-info/reset',
  RESET_ALL_DATA: '/api/v1/settings/reset-data',
  APP_CONFIG: '/api/v1/settings/app-config',
  /** Grouped backend settings (shop/currency/pos/stock/telegram/invoice/system). */
  ADMIN_SETTINGS: '/api/v1/admin/settings',
  APP_CONFIG_TEST_EMAIL: '/api/v1/settings/app-config/email/test-connection',
  APP_CONFIG_SEND_TEST_EMAIL: '/api/v1/settings/app-config/email/send-test',
  APP_CONFIG_TEST_TELEGRAM: '/api/v1/settings/app-config/telegram/test-connection',
  APP_CONFIG_SEND_TEST_TELEGRAM: '/api/v1/settings/app-config/telegram/send-test',
  STORAGE_PROVIDERS: '/api/v1/settings/storage',
  STORAGE_PROVIDER: (id: string) => `/api/v1/settings/storage/${id}`,
  STORAGE_PROVIDER_TEST: (id: string) => `/api/v1/settings/storage/${id}/test-connection`,
  STORAGE_PROVIDER_SET_DEFAULT: (id: string) => `/api/v1/settings/storage/${id}/set-default`,
  STORAGE_PROVIDER_SET_ACTIVE: (id: string) => `/api/v1/settings/storage/${id}/set-active`,

  SEARCH: '/api/v1/search',
} as const

/**
 * Canonical collection → endpoint mapping used by entity repositories.
 * Frontend collection names map to `/api/v1` resource paths.
 */
export const CollectionEndpoints = {
  categories: ApiEndpoints.CATEGORIES,
  uoms: ApiEndpoints.UOMS,
  brands: ApiEndpoints.BRANDS,
  products: ApiEndpoints.PRODUCTS,
  suppliers: ApiEndpoints.SUPPLIERS,
  customers: ApiEndpoints.CUSTOMERS,
  sales: ApiEndpoints.REPORT_SALES,
  deliveryNotes: ApiEndpoints.DELIVERY_NOTES,
  // Purchase Report reads the report path; creating stock-in goes through
  // ApiEndpoints.STOCK_IN (PosCommandRepository.createStockOperation).
  stockIns: ApiEndpoints.REPORT_PURCHASES,
  saleReturns: ApiEndpoints.REPORT_SALE_RETURNS,
  purchaseReturns: ApiEndpoints.REPORT_PURCHASE_RETURNS,
  stockMovements: ApiEndpoints.STOCK_MOVEMENTS,
  // Sale-price rows are product-scoped (PRODUCT_SALE_PRICES(productId)); this
  // collection key exists for mock compatibility only and is never flat CRUD
  // against the backend.
  productSalePrices: ApiEndpoints.PRODUCTS,
  customerDebtPayments: ApiEndpoints.CUSTOMERS,
  customerDebts: ApiEndpoints.CUSTOMER_DEBTS,
  supplierDebtPayments: ApiEndpoints.SUPPLIERS,
  supplierDebts: ApiEndpoints.SUPPLIER_DEBTS,
  // Operating-expense list rows come from the finance ledger (entries);
  // creation goes through POST /reports/finance/expenses.
  expenses: ApiEndpoints.FINANCE_ENTRIES,
  users: ApiEndpoints.USERS,
  roles: ApiEndpoints.ROLES,
  documentSequences: ApiEndpoints.DOCUMENT_SEQUENCES,
  auditLogs: ApiEndpoints.AUDIT_LOGS,
} as const

export type ApiCollection = keyof typeof CollectionEndpoints

export function isApiCollection(collection: string): collection is ApiCollection {
  return collection in CollectionEndpoints
}
