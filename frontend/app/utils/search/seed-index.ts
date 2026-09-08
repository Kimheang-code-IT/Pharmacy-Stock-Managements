import type { IndexedDocument, SearchEntityType } from '~/types/stock-pos/search'
import {
  isSearchIndexSeeded,
  markSearchIndexSeeded,
  upsertIndexedDocuments,
} from '~/utils/search/search-index'

export function ensureSearchIndexSeeded() {
  if (!import.meta.client) return
  if (isSearchIndexSeeded()) return
  upsertIndexedDocuments([] as IndexedDocument[])
  markSearchIndexSeeded()
}

export function sourceLabelFor(entityType: SearchEntityType): string {
  const map: Record<SearchEntityType, string> = {
    navigation: 'Navigation',
    document: 'Document',
    file: 'File',
    attachment: 'Attachment',
    user: 'User',
    other: 'Record',
  }
  return map[entityType] || 'Record'
}
