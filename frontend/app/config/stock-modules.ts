import type { ModuleField, ModuleConfig } from './modules'
import { ACTIVE_STATUS } from './shared-options'

/**
 * Stock & POS master-data and report modules. Registered into the
 * route-module lookup by `modules.ts` and rendered by the generic
 * workspace/document components.
 */

const f = (
  key: string,
  label: string,
  section = 'General Information',
  type: ModuleField['type'] = 'text',
  options?: ModuleField['options'],
  extra: Partial<ModuleField> = {},
): ModuleField => ({ key, label, labelKm: label, section, sectionKm: section, type, options, ...extra })

const col = (key: string, label: string, extra: Partial<ModuleField> = {}): ModuleField => ({
  key,
  label,
  labelKm: label,
  ...extra,
})

function createModule(partial: Omit<ModuleConfig, 'canCreate' | 'titleKm' | 'singularKm' | 'descriptionKm'> & {
  canCreate?: boolean
  titleKm?: string
  singularKm?: string
  descriptionKm?: string
}): ModuleConfig {
  return {
    ...partial,
    canCreate: partial.readOnly ? false : partial.canCreate !== false,
    kind: partial.kind || 'standard',
    titleKm: partial.titleKm || partial.title,
    singularKm: partial.singularKm || partial.singular,
    descriptionKm: partial.descriptionKm || partial.description,
  }
}

const PAYMENT_METHODS = ['Cash', 'Card', 'Mobile Payment', 'Bank Transfer', 'Credit'] as const
const SALE_STATUS = ['Paid', 'Partial', 'Unpaid', 'Returned'] as const
const DEBT_STATUS = ['UNPAID', 'PARTIAL', 'PAID'] as const
const STOCK_MOVEMENT_TYPES = ['Stock In', 'Sale', 'Adjustment', 'Damage', 'Expiry', 'Sale Return'] as const
const ACTIVE_INACTIVE = ACTIVE_STATUS

export const stockModules: ModuleConfig[] = [
  createModule({
    path: '/setup/categories',
    title: 'Categories',
    singular: 'Category',
    description: 'Product categories used to group stock items.',
    icon: 'i-lucide-tags',
    group: 'master',
    permission: 'categories.view',
    collection: 'categories',
    titleField: 'name',
    columns: [
      col('code', 'Code'),
      col('name', 'Name'),
      col('description', 'Description'),
      col('productCount', 'Products'),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Name', 'General Information', 'text', undefined, { required: true }),
      f('code', 'Code', 'General Information', 'text', undefined, { help: 'Unique short code. Leave blank to let the system generate one.' }),
      f('description', 'Description', 'General Information', 'textarea', undefined, { colSpan: 2 }),
      f('status', 'Status', 'Status', 'select', ACTIVE_INACTIVE, { required: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', ACTIVE_INACTIVE),
    ],
  }),
  createModule({
    path: '/setup/uoms',
    title: 'Units of Measure',
    singular: 'Unit of Measure',
    description: 'Units of measure (UOM) used by products, e.g. pcs, box, kg. UOMs linked to products should be disabled instead of deleted.',
    icon: 'i-lucide-ruler',
    group: 'master',
    permission: 'uom.view',
    collection: 'uoms',
    titleField: 'name',
    columns: [
      col('code', 'Code'),
      col('name', 'Name'),
      col('symbol', 'Symbol'),
      col('description', 'Description'),
      col('productCount', 'Products'),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Name', 'General Information', 'text', undefined, { required: true }),
      f('code', 'Code', 'General Information', 'text', undefined, { help: 'Unique short code. Leave blank to let the system generate one.' }),
      f('symbol', 'Symbol', 'General Information', 'text', undefined, { required: true, help: 'Short form shown on lists and invoices, e.g. pcs, box, kg.' }),
      f('description', 'Description', 'General Information', 'textarea', undefined, { colSpan: 2 }),
      f('status', 'Status', 'Status', 'select', ACTIVE_INACTIVE, { required: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', ACTIVE_INACTIVE),
    ],
  }),
  createModule({
    path: '/setup/brands',
    title: 'Brands',
    singular: 'Brand',
    description: 'Product brands used to group stock items by manufacturer.',
    icon: 'i-lucide-award',
    group: 'master',
    permission: 'brand.view',
    collection: 'brands',
    titleField: 'name',
    columns: [
      col('code', 'Code'),
      col('name', 'Name'),
      col('description', 'Description'),
      col('productCount', 'Products'),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Brand Name', 'General Information', 'text', undefined, { required: true }),
      f('code', 'Code', 'General Information', 'text', undefined, { help: 'Unique short code. Leave blank to let the system generate one.' }),
      f('logo', 'Logo', 'General Information', 'image', undefined, { help: 'Optional brand logo.' }),
      f('description', 'Description', 'General Information', 'textarea', undefined, { colSpan: 2 }),
      f('status', 'Status', 'Status', 'select', ACTIVE_INACTIVE, { required: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', ACTIVE_INACTIVE),
    ],
  }),
  createModule({
    path: '/stock',
    title: 'Stock',
    singular: 'Product',
    description: 'Products with current stock, cost and pricing. Stock in, adjustment, damage and expiry run as actions from this page.',
    icon: 'i-lucide-package',
    group: 'master',
    permission: 'products.view',
    collection: 'products',
    titleField: 'name',
    documentForm: 'product',
    columns: [
      col('imageUrl', 'Image', { labelKm: 'រូបភាព', type: 'image' }),
      col('code', 'Code'),
      col('name', 'Product'),
      col('category', 'Category'),
      col('brand', 'Brand', { labelKm: 'ម៉ាក' }),
      col('barcode', 'Barcode'),
      col('uomSymbol', 'UOM'),
      col('stockInQty', 'Stock In'),
      col('stockOutQty', 'Stock Out'),
      col('quantity', 'Current Stock'),
      col('damageQty', 'Damage'),
      col('costPrice', 'Cost'),
      col('salePrice', 'Price'),
      col('expiryDate', 'Expire Date', { labelKm: 'ថ្ងៃផុតកំណត់', type: 'date' }),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Product Name', 'General Information', 'text', undefined, { required: true, labelKey: 'app.modules.products.fields.name' }),
      f('categoryId', 'Category', 'General Information', 'select', undefined, { required: true, optionsCollection: 'categories' }),
      f('imageUrl', 'Image', 'General Information', 'image'),
      f('brandId', 'Brand', 'General Information', 'select', undefined, { optionsCollection: 'brands' }),
      f('barcode', 'Barcode', 'General Information', 'text'),
      f('uomId', 'Unit of Measure', 'General Information', 'select', undefined, { required: true, optionsCollection: 'uoms' }),
      f('supplierId', 'Supplier', 'General Information', 'select', undefined, { optionsCollection: 'suppliers' }),
      // Spec §5.9 General tab: identity + cost price + read-only current
      // stock. Sale price lives on the Pricing tab, expiry on the Expire tab.
      f('costPrice', 'Cost Price', 'General Information', 'number', undefined, { required: true }),
      f('quantity', 'Current Stock', 'General Information', 'number', undefined, { computed: true, help: 'Current stock. Change it through stock operations.' }),
      f('status', 'Status', 'Status', 'select', ['Active', 'Inactive', 'Low Stock'], { computed: true }),
    ],
    filters: [
      f('category', 'Category', '', 'select'),
      f('status', 'Status', '', 'select', ['Active', 'Low Stock', 'Inactive']),
    ],
  }),
  createModule({
    path: '/setup/suppliers',
    title: 'Suppliers',
    singular: 'Supplier',
    description: 'Supplier master records. Search purchase and debt history on Reports.',
    icon: 'i-lucide-truck',
    group: 'master',
    permission: 'suppliers.view',
    collection: 'suppliers',
    titleField: 'name',
    columns: [
      col('code', 'Code'),
      col('name', 'Supplier'),
      col('phone', 'Phone'),
      col('location', 'Location'),
      col('totalDebt', 'Outstanding Debt'),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Supplier Name', 'General Information', 'text', undefined, { required: true }),
      f('phone', 'Phone', 'General Information', 'text', undefined, { required: true }),
      f('location', 'Location', 'General Information', 'textarea'),
      f('status', 'Status', 'Status', 'select', ACTIVE_INACTIVE, { required: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', ACTIVE_INACTIVE),
    ],
  }),
  createModule({
    path: '/setup/customers',
    title: 'Customers',
    singular: 'Customer',
    description: 'Customer master records. Search sales, debt and delivery history on Reports.',
    icon: 'i-lucide-users',
    group: 'master',
    permission: 'customers.view',
    collection: 'customers',
    titleField: 'name',
    columns: [
      col('code', 'Code'),
      col('name', 'Customer'),
      col('phone', 'Phone'),
      col('location', 'Location'),
      col('debtBalance', 'Outstanding Debt'),
      col('status', 'Status'),
    ],
    fields: [
      f('name', 'Customer Name', 'General Information', 'text', undefined, { required: true }),
      f('phone', 'Phone', 'General Information', 'text', undefined, { required: true }),
      f('location', 'Location', 'General Information', 'textarea'),
      f('status', 'Status', 'Status', 'select', ACTIVE_INACTIVE, { required: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', ACTIVE_INACTIVE),
    ],
  }),

  /* ------------------------- Reports ------------------------- */

  createModule({
    path: '/reports/sales',
    title: 'Sales Report',
    singular: 'Sale',
    description: 'Completed sales with payment status and totals.',
    icon: 'i-lucide-receipt',
    group: 'reports',
    permission: 'reports.view',
    collection: 'sales',
    titleField: 'saleNo',
    kind: 'reports',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('saleNo', 'Sale No'),
      col('date', 'Date'),
      col('customer', 'Customer'),
      col('lineCount', 'Items'),
      col('subtotal', 'Subtotal'),
      col('discount', 'Discount'),
      col('total', 'Total'),
      col('paidAmount', 'Paid'),
      col('remaining', 'Remaining'),
      col('paymentMethod', 'Payment Method'),
      col('status', 'Status'),
    ],
    fields: [
      f('saleNo', 'Sale No', 'Sale', 'text', undefined, { computed: true }),
      f('date', 'Date', 'Sale', 'date'),
      f('customer', 'Customer', 'Sale'),
      f('paymentMethod', 'Payment Method', 'Sale', 'select', PAYMENT_METHODS),
      f('total', 'Total', 'Totals', 'number', undefined, { computed: true }),
    ],
    filters: [
      f('customer', 'Customer', '', 'select'),
      f('status', 'Status', '', 'select', SALE_STATUS),
      f('paymentMethod', 'Payment Method', '', 'select', PAYMENT_METHODS),
    ],
  }),
  createModule({
    path: '/reports/purchases',
    title: 'Purchase Report',
    singular: 'Purchase',
    description: 'Stock-in and purchase history per supplier.',
    icon: 'i-lucide-shopping-cart',
    group: 'reports',
    permission: 'reports.view',
    collection: 'stockIns',
    titleField: 'purchaseNo',
    kind: 'reports',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('purchaseNo', 'Purchase No'),
      col('date', 'Date'),
      col('supplier', 'Supplier'),
      col('lineCount', 'Items'),
      col('total', 'Total'),
      col('paidAmount', 'Paid'),
      col('remaining', 'Remaining'),
      col('status', 'Status'),
    ],
    fields: [
      f('purchaseNo', 'Purchase No', 'Purchase', 'text', undefined, { computed: true }),
      f('date', 'Date', 'Purchase', 'date'),
      f('supplier', 'Supplier', 'Purchase'),
      f('total', 'Total', 'Totals', 'number', undefined, { computed: true }),
    ],
    filters: [
      f('supplier', 'Supplier', '', 'select'),
      f('status', 'Status', '', 'select', ['Completed', 'Partial']),
    ],
  }),
  createModule({
    path: '/reports/customer-debts',
    title: 'Customer Debt Report',
    singular: 'Customer Debt',
    description: 'Invoice-level customer debts with invoice total, paid and remaining amounts.',
    icon: 'i-lucide-hand-coins',
    group: 'reports',
    permission: 'reports.view',
    collection: 'customerDebts',
    titleField: 'invoiceNo',
    kind: 'reports',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('date', 'Date', { type: 'date' }),
      col('invoiceNo', 'Invoice No.'),
      col('customer', 'Customer'),
      col('invoiceTotal', 'Invoice Total'),
      col('paidAmount', 'Paid Amount'),
      col('remainingAmount', 'Remaining Amount'),
      col('dueDate', 'Due Date', { type: 'date' }),
      col('status', 'Status'),
    ],
    fields: [
      f('date', 'Date', 'Debt', 'date'),
      f('invoiceNo', 'Invoice No.', 'Debt', 'text', undefined, { computed: true }),
      f('customer', 'Customer', 'Debt', 'text', undefined, { computed: true }),
      f('invoiceTotal', 'Invoice Total', 'Debt', 'number', undefined, { computed: true }),
      f('paidAmount', 'Paid Amount', 'Debt', 'number', undefined, { computed: true }),
      f('remainingAmount', 'Remaining Amount', 'Debt', 'number', undefined, { computed: true }),
      f('dueDate', 'Due Date', 'Debt', 'date'),
    ],
    filters: [
      f('customer', 'Customer', '', 'select'),
      f('status', 'Status', '', 'select', DEBT_STATUS),
    ],
  }),
  createModule({
    path: '/reports/supplier-debts',
    title: 'Supplier Debt Report',
    singular: 'Supplier Debt',
    description: 'Document-level supplier debts with purchase total, paid and remaining amounts.',
    icon: 'i-lucide-landmark',
    group: 'reports',
    permission: 'reports.view',
    collection: 'supplierDebts',
    titleField: 'purchaseNo',
    kind: 'reports',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('date', 'Date', { type: 'date' }),
      col('purchaseNo', 'Invoice No. / Purchase No.'),
      col('supplier', 'Supplier'),
      col('totalAmount', 'Total Amount'),
      col('paidAmount', 'Paid Amount'),
      col('remainingAmount', 'Remaining Amount'),
      col('dueDate', 'Due Date', { type: 'date' }),
      col('status', 'Status'),
    ],
    fields: [
      f('date', 'Date', 'Debt', 'date'),
      f('purchaseNo', 'Invoice No. / Purchase No.', 'Debt', 'text', undefined, { computed: true }),
      f('supplier', 'Supplier', 'Debt', 'text', undefined, { computed: true }),
      f('totalAmount', 'Total Amount', 'Debt', 'number', undefined, { computed: true }),
      f('paidAmount', 'Paid Amount', 'Debt', 'number', undefined, { computed: true }),
      f('remainingAmount', 'Remaining Amount', 'Debt', 'number', undefined, { computed: true }),
      f('dueDate', 'Due Date', 'Debt', 'date'),
    ],
    filters: [
      f('supplier', 'Supplier', '', 'select'),
      f('status', 'Status', '', 'select', DEBT_STATUS),
    ],
  }),

  /* ----------------------- Stock history --------------------- */

  createModule({
    path: '/stock/movements',
    title: 'Stock Movements',
    singular: 'Movement',
    description: 'Immutable stock movement history across all operations.',
    icon: 'i-lucide-arrow-left-right',
    group: 'master',
    permission: 'products.view',
    collection: 'stockMovements',
    titleField: 'reference',
    kind: 'reports',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('date', 'Date'),
      col('product', 'Product'),
      col('type', 'Type'),
      col('quantity', 'Qty'),
      col('reference', 'Reference'),
      col('user', 'User'),
      col('note', 'Note'),
    ],
    fields: [],
    filters: [
      f('type', 'Type', '', 'select', STOCK_MOVEMENT_TYPES),
    ],
  }),
]