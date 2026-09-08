import type { DocumentFieldSchema } from '~/types/stock-pos/common'

export type DocumentFormField = DocumentFieldSchema

export type DocumentFormSectionItem
  = | { kind: 'field', field: DocumentFormField }
    | { kind: 'image-pair', left: DocumentFormField[], image: DocumentFormField }

/** Fields that are never allowed on the left side of an image pair. */
function isFullWidthField(field: DocumentFormField) {
  return field.colSpan === 2
    || field.type === 'textarea'
    || field.type === 'permission-matrix'
    || field.type === 'notification-rules'
    || field.type === 'connection-status'
    || field.type === 'alert'
    || field.type === 'line-table'
    || field.type === 'uom-conversions'
    || field.type === 'related-records'
}

/** Normal single-column fields that may sit to the left of an image upload. */
function isPairLeftField(field: DocumentFormField) {
  return field.type !== 'textarea' && field.type !== 'image' && !isFullWidthField(field)
}

/** Image uploads inside a pair render in a compact side column. */
function pairImageField(field: DocumentFormField): DocumentFormField {
  return { ...field, meta: { ...field.meta, compact: true } }
}

/**
 * Group each image upload with the one or two normal fields that directly
 * precede it: they stack on the left while the upload sits on the right
 * (desktop `sm+`). Mobile keeps the natural stacked order (fields first).
 * An image without preceding plain fields stays a normal single field.
 */
export function documentFormSectionItems(fields: DocumentFormField[]): DocumentFormSectionItem[] {
  const items: DocumentFormSectionItem[] = []
  let i = 0
  while (i < fields.length) {
    const first = fields[i]
    const second = fields[i + 1]
    const third = fields[i + 2]
    if (first && second && third && isPairLeftField(first) && isPairLeftField(second) && third.type === 'image') {
      items.push({ kind: 'image-pair', left: [first, second], image: pairImageField(third) })
      i += 3
      continue
    }
    if (first && second?.type === 'image' && isPairLeftField(first)) {
      items.push({ kind: 'image-pair', left: [first], image: pairImageField(second) })
      i += 2
      continue
    }
    if (first) items.push({ kind: 'field', field: first })
    i += 1
  }
  return items
}

/** Stable per-item key for `v-for` inside a section. */
export function documentFormItemKey(item: DocumentFormSectionItem, index: number) {
  return item.kind === 'image-pair' ? `pair-${item.image.key}` : `field-${index}-${item.field.key}`
}
