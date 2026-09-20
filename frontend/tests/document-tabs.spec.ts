import { describe, expect, it } from 'vitest'
import type { ModuleConfig } from '../app/config/modules'
import { stockModules } from '../app/config/stock-modules'
import { moduleDocumentTabs } from '../app/utils/module/document-tabs'

function moduleFixture(overrides: Partial<ModuleConfig> = {}): ModuleConfig {
  return {
    path: '/records',
    title: 'Records',
    titleKm: 'Records',
    singular: 'Record',
    singularKm: 'Record',
    description: '',
    descriptionKm: '',
    icon: 'i-lucide-file',
    group: 'test',
    permission: 'records.view',
    collection: 'records',
    titleField: 'name',
    columns: [],
    fields: [
      { key: 'name', label: 'Name', section: 'General', type: 'text' },
      { key: 'status', label: 'Status', section: 'Status', type: 'select', options: ['Active', 'Inactive'] },
    ],
    statuses: ['Active', 'Inactive'],
    ...overrides,
  }
}

describe('product document tabs (spec §5.9)', () => {
  const productModule = stockModules.find(item => item.collection === 'products')!

  it('has exactly General | Pricing | Batches | Barcode — no Expire or Convert UOM tab', () => {
    const tabs = moduleDocumentTabs(productModule)
    expect(tabs.map(tab => tab.id)).toEqual(['general', 'pricing', 'batches', 'barcode'])
    expect(tabs.map(tab => tab.labelKey)).toEqual([
      'app.stock.tabGeneral',
      'app.stock.tabPricing',
      'app.stock.tabBatches',
      'app.stock.tabBarcode',
    ])
  })

  it('keeps General to identity fields (cost price / current stock removed)', () => {
    const tabs = moduleDocumentTabs(productModule)
    const generalKeys = tabs[0]!.sections.flatMap(section =>
      section.fields.map(field => field.key))
    expect(generalKeys).toContain('name')
    expect(generalKeys).toContain('categoryId')
    expect(generalKeys).toContain('uomId')
    expect(generalKeys).toContain('supplierId')
    // Cost Price and Current Stock are not editable document fields.
    expect(generalKeys).not.toContain('costPrice')
    expect(generalKeys).not.toContain('quantity')
    // Sale price lives on the Pricing tab.
    expect(generalKeys).not.toContain('salePrice')
  })

  it('binds the Pricing tab to uomConversions with the exact column contract', () => {
    const tabs = moduleDocumentTabs(productModule)
    const pricingField = tabs[1]!.sections.flatMap(s => s.fields).find(f => f.key === 'uomConversions')
    expect(pricingField?.type).toBe('uom-conversions')
    expect(pricingField?.colSpan).toBe(2)
  })

  it('hides the Stock Costing toggles and the read-only Expire Date', () => {
    const tabs = moduleDocumentTabs(productModule)
    const general = tabs[0]!
    expect(general.sections.some(s => s.id === 'stock-costing' || s.id === 'stock-expire')).toBe(false)
    const keys = general.sections.flatMap(s => s.fields.map(f => f.key))
    expect(keys).not.toContain('trackBatch')
    expect(keys).not.toContain('expiryTracking')
    expect(keys).not.toContain('fifo')
    expect(keys).not.toContain('expiryDate')
  })

  it('create mode hides Pricing, Barcode, Expire Date/batches and the Movements tab', () => {
    const tabs = moduleDocumentTabs(productModule, { isCreate: true })
    expect(tabs.map(tab => tab.id)).toEqual(['general'])

    const sections = tabs.flatMap(tab => tab.sections)
    expect(sections.some(section => section.id === 'stock-expire')).toBe(false)
    expect(sections.some(section => section.id === 'stock-costing')).toBe(false)

    const keys = sections.flatMap(section => section.fields.map(field => field.key))
    expect(keys).not.toContain('barcode')
    expect(keys).not.toContain('uomConversions')
    expect(keys).not.toContain('expiryDate')
    expect(keys).not.toContain('trackBatch')
    // Editable create inputs stay.
    expect(keys).toContain('name')
    expect(keys).toContain('uomId')
  })
})

describe('document lifecycle status', () => {
  it('omits status fields and their now-empty sections from generated forms', () => {
    const tabs = moduleDocumentTabs(moduleFixture())
    const sections = tabs.flatMap(tab => tab.sections)
    const fields = sections.flatMap(section => section.fields)

    expect(fields.some(field => field.key === 'status')).toBe(false)
    expect(sections.some(section => section.id === 'status')).toBe(false)
    expect(fields.some(field => field.key === 'name')).toBe(true)
  })

  it('omits Active/Inactive status from the user form', () => {
    const tabs = moduleDocumentTabs(moduleFixture({
      path: '/administration/users',
      collection: 'users',
      permission: 'admin.users.view',
    }))
    const fields = tabs.flatMap(tab => tab.sections.flatMap(section => section.fields))
    expect(fields.some(field => field.key === 'status')).toBe(false)
  })

  it('also removes status from custom module tabs', () => {
    const tabs = moduleDocumentTabs(moduleFixture({
      tabs: [{
        id: 'details',
        sections: [{
          id: 'main',
          fields: [
            { key: 'name', labelKey: 'name', type: 'text' },
            { key: 'status', labelKey: 'status', type: 'select' },
          ],
        }],
      }],
    }))

    expect(tabs[0]?.sections[0]?.fields.map(field => field.key)).toEqual(['name'])
  })

  it('does not add a Stock History related tab on product documents', () => {
    const module = stockModules.find(item => item.collection === 'products')
    expect(module).toBeTruthy()
    expect(module!.related?.length ?? 0).toBe(0)

    const tabs = moduleDocumentTabs(module!, { includeRelated: true })
    expect(tabs.some(tab => tab.id === 'related')).toBe(false)
  })

  it('keeps outstanding debt on customer and supplier lists, not on documents', () => {
    for (const collection of ['customers', 'suppliers'] as const) {
      const module = stockModules.find(item => item.collection === collection)
      expect(module).toBeTruthy()
      const debtKey = collection === 'customers' ? 'debtBalance' : 'totalDebt'
      expect(module!.columns.some(column => column.key === debtKey)).toBe(true)
      expect(module!.fields.some(field => field.key === debtKey)).toBe(false)

      const formKeys = moduleDocumentTabs(module!).flatMap(tab =>
        tab.sections.flatMap(section => section.fields.map(field => field.key)),
      )
      expect(formKeys).not.toContain(debtKey)
    }
  })
})

describe('customer / supplier party document tabs', () => {
  const customer = stockModules.find(item => item.collection === 'customers')!
  const supplier = stockModules.find(item => item.collection === 'suppliers')!

  it('registers the party document form on both master modules', () => {
    expect(customer.documentForm).toBe('party')
    expect(supplier.documentForm).toBe('party')
  })

  it('gives customers General | History', () => {
    const tabs = moduleDocumentTabs(customer)
    expect(tabs.map(tab => tab.id)).toEqual(['general', 'history'])
    expect(tabs.map(tab => tab.labelKey)).toEqual([
      'app.sections.general',
      'app.party.tabs.history',
    ])
  })

  it('gives suppliers General | History', () => {
    const tabs = moduleDocumentTabs(supplier)
    expect(tabs.map(tab => tab.id)).toEqual(['general', 'history'])
    expect(tabs.map(tab => tab.labelKey)).toEqual([
      'app.sections.general',
      'app.party.tabs.history',
    ])
  })

  it('binds the history tab to its customer/supplier panel type', () => {
    const customerFields = moduleDocumentTabs(customer).flatMap(tab =>
      tab.sections.flatMap(section => section.fields))
    const supplierFields = moduleDocumentTabs(supplier).flatMap(tab =>
      tab.sections.flatMap(section => section.fields))

    expect(customerFields.find(f => f.type === 'party-sales-history')?.meta?.kind).toBe('customer')
    expect(customerFields.some(f => f.type === 'party-purchase-history')).toBe(false)

    expect(supplierFields.find(f => f.type === 'party-purchase-history')?.meta?.kind).toBe('supplier')
    expect(supplierFields.some(f => f.type === 'party-sales-history')).toBe(false)
  })

  it('keeps only the General tab while creating a party', () => {
    expect(moduleDocumentTabs(customer, { isCreate: true }).map(tab => tab.id)).toEqual(['general'])
    expect(moduleDocumentTabs(supplier, { isCreate: true }).map(tab => tab.id)).toEqual(['general'])
  })
})

describe('debt report currency filter (spec 2.1.10)', () => {
  it('exposes a USD | KHR currency filter on both debt reports', () => {
    for (const collection of ['customerDebts', 'supplierDebts'] as const) {
      const module = stockModules.find(item => item.collection === collection)!
      const currencyFilter = module.filters?.find(filter => filter.key === 'currency')
      expect(currencyFilter).toBeTruthy()
      expect(currencyFilter?.type).toBe('select')
      expect(currencyFilter?.options).toEqual(['USD', 'KHR'])
    }
  })
})
