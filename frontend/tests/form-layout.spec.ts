import { describe, expect, it } from 'vitest'
import { documentFormItemKey, documentFormSectionItems } from '~/utils/module/form-layout'
import type { DocumentFieldSchema } from '~/types/stock-pos/common'

function field(key: string, type: DocumentFieldSchema['type'] = 'text', extra: Partial<DocumentFieldSchema> = {}): DocumentFieldSchema {
  return { key, label: key, type, ...extra }
}

describe('documentFormSectionItems', () => {
  it('groups two plain fields with a trailing image into an image pair', () => {
    const items = documentFormSectionItems([
      field('name'),
      field('categoryId', 'select'),
      field('imageUrl', 'image'),
      field('brandId', 'select'),
    ])

    expect(items).toEqual([
      { kind: 'image-pair', left: [expect.objectContaining({ key: 'name' }), expect.objectContaining({ key: 'categoryId' })], image: expect.objectContaining({ key: 'imageUrl' }) },
      { kind: 'field', field: expect.objectContaining({ key: 'brandId' }) },
    ])
    expect(items[0]?.kind === 'image-pair' && items[0].image.meta?.compact).toBe(true)
  })

  it('groups a single plain field with a trailing image', () => {
    const items = documentFormSectionItems([
      field('supportEmail'),
      field('supportPhone'),
      field('logo', 'image'),
    ])

    expect(items).toHaveLength(1)
    expect(items[0]?.kind === 'image-pair' && items[0].left.map(f => f.key)).toEqual(['supportEmail', 'supportPhone'])
  })

  it('keeps brand name + code + logo as a pair without reordering', () => {
    const items = documentFormSectionItems([
      field('name'),
      field('code'),
      field('logo', 'image'),
      field('description', 'textarea', { colSpan: 2 }),
      field('status', 'select'),
    ])

    expect(items.map(item => item.kind)).toEqual(['image-pair', 'field', 'field'])
  })

  it('renders a lone image as a normal field, not a forced pair', () => {
    const items = documentFormSectionItems([field('imageUrl', 'image', { colSpan: 2 })])

    expect(items).toEqual([{ kind: 'field', field: expect.objectContaining({ key: 'imageUrl' }) }])
  })

  it('does not pair across full-width or textarea fields', () => {
    const items = documentFormSectionItems([
      field('description', 'textarea'),
      field('name'),
      field('logo', 'image'),
    ])

    expect(items.map(item => item.kind)).toEqual(['field', 'image-pair'])
    expect(items[1]?.kind === 'image-pair' && items[1].left.map(f => f.key)).toEqual(['name'])
  })

  it('produces stable keys for v-for', () => {
    const items = documentFormSectionItems([
      field('name'),
      field('categoryId', 'select'),
      field('imageUrl', 'image'),
      field('brandId', 'select'),
    ])

    expect(documentFormItemKey(items[0]!, 0)).toBe('pair-imageUrl')
    expect(documentFormItemKey(items[1]!, 1)).toBe('field-1-brandId')
  })
})
