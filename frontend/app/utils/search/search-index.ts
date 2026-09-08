/**
 * Phase 2 search index — localStorage-backed document corpus for Cmd+K.
 */
import type { IndexedDocument } from '~/types/stock-pos/search'
import { localStore } from '~/utils/storage/local'

const INDEX_KEY = 'stockpos:search:index:v1'
const SEEDED_KEY = 'stockpos:search:index:seeded:v1'

function readAll(): IndexedDocument[] {
  return localStore.get<IndexedDocument[]>(INDEX_KEY) || []
}

function writeAll(docs: IndexedDocument[]) {
  localStore.set(INDEX_KEY, docs)
}

export function listIndexedDocuments(): IndexedDocument[] {
  if (!import.meta.client) return []
  return readAll()
}

export function upsertIndexedDocument(doc: IndexedDocument) {
  if (!import.meta.client) return
  const rows = readAll()
  const idx = rows.findIndex(r => r.id === doc.id)
  if (idx >= 0) rows[idx] = doc
  else rows.push(doc)
  writeAll(rows)
}

export function upsertIndexedDocuments(docs: IndexedDocument[]) {
  if (!import.meta.client || !docs.length) return
  const map = new Map(readAll().map(d => [d.id, d]))
  for (const doc of docs) map.set(doc.id, doc)
  writeAll([...map.values()])
}

export function isSearchIndexSeeded(): boolean {
  if (!import.meta.client) return false
  return localStore.get<boolean>(SEEDED_KEY) === true
}

export function markSearchIndexSeeded() {
  if (!import.meta.client) return
  localStore.set(SEEDED_KEY, true)
}

