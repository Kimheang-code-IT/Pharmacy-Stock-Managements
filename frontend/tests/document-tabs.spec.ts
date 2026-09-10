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

  it('has exactly General | Pricing | Expire — no Convert UOM tab', () => {
    const tabs = moduleDocumentTabs(productModule)
    expect(tabs.map(tab => tab.id)).toEqual(['general', 'pricing', 'expire'])
    expect(tabs.map(tab => tab.labelKey)).toEqual([
      'app.stock.tabGeneral',
      'app.stock.tabPricing',
      'app.stock.tabExpire',
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
    // Moved to Pricing / Expire tabs.
    expect(generalKeys).not.toContain('salePrice')
    expect(generalKeys).not.toContain('expiryTracking')
    expect(generalKeys).not.toContain('expiryDate')
  })

  it('binds the Pricing tab to uomConversions with the exact column contract', () => {
    const tabs = moduleDocumentTabs(productModule)
    const pricingField = tabs[1]!.sections.flatMap(s => s.fields).find(f => f.key === 'uomConversions')
    expect(pricingField?.type).toBe('uom-conversions')
    expect(pricingField?.colSpan).toBe(2)
  })

  it('owns Track Expiry + read-only Expire Date on the Expire tab', () => {
    const tabs = moduleDocumentTabs(productModule)
    const fields = tabs[2]!.sections.flatMap(s => s.fields)
    const tracking = fields.find(f => f.key === 'expiryTracking')
    const expiry = fields.find(f => f.key === 'expiryDate')
    expect(tracking?.type).toBe('boolean')
    expect(expiry?.type).toBe('date')
    expect(expiry?.readOnly).toBe(true)
    // No raw i18n keys — every label/help resolves to a defined locale entry.
    for (const field of fields) {
      expect(field.labelKey).toMatch(/^app\.stock\./)
      expect(field.helpKey).toMatch(/^app\.stock\./)
    }
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
