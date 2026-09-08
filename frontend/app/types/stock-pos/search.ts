/**
 * Global Cmd+K search types.
 */

export type SearchMode = 'keyword' | 'semantic'

export type SearchEntityType =
  | 'navigation'
  | 'document'
  | 'file'
  | 'attachment'
  | 'user'
  | 'other'

export interface IndexedDocument {
  id: string
  entityType: SearchEntityType
  entityId: string
  title: string
  text: string
  url: string
  /** Entity permission code — empty = always visible when logged in */
  permission: string
  mimeType?: string
  updatedAt: string
}

export interface SearchHit extends IndexedDocument {
  score: number
  snippet: string
  sourceLabel: string
}

export interface AiSearchAnswer {
  answer: string
  citations: SearchHit[]
}

export interface SearchQueryOptions {
  limit?: number
}
