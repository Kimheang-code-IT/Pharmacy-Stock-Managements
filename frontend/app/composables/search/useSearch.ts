import type {
  AiSearchAnswer,
  SearchHit,
  SearchQueryOptions,
} from '~/types/stock-pos/search'
import { useSearchRepository } from '~/repositories/index'

/** Map a backend `{ hits, total }` search response to the UI hit type. */
export function adaptBackendSearchHits(
  hits: Array<{ id: string, type: string, title: string, subtitle?: string | null, url: string }>,
): SearchHit[] {
  const entityTypeFromBackend = (type: string): SearchHit['entityType'] => {
    if (type === 'user') return 'user'
    return 'document'
  }
  const sourceLabelFromBackend = (type: string): string => {
    const labels: Record<string, string> = {
      product: 'Stock',
      customer: 'Customers',
      supplier: 'Suppliers',
      sale: 'Sales',
      user: 'Users',
    }
    return labels[type] || 'Records'
  }
  return hits.map(hit => ({
    id: hit.id,
    entityType: entityTypeFromBackend(hit.type),
    entityId: hit.id,
    title: hit.title,
    text: hit.subtitle || '',
    url: hit.url,
    permission: '',
    updatedAt: '',
    score: 1,
    snippet: hit.subtitle || '',
    sourceLabel: sourceLabelFromBackend(hit.type),
  }))
}

export function useSearch() {
  const searchRepository = useSearchRepository()

  async function searchKeyword(query: string, options: SearchQueryOptions = {}) {
    const limit = options.limit ?? 12
    const hits = await searchRepository.search(query, limit)
    return adaptBackendSearchHits(hits)
  }

  async function searchSemantic(query: string, options: SearchQueryOptions = {}) {
    return searchKeyword(query, options)
  }

  async function askAi(query: string, hits: SearchHit[]): Promise<AiSearchAnswer> {
    const citations = hits.slice(0, 5)
    if (!citations.length) {
      return {
        answer: `No records matched “${query.trim()}”.`,
        citations: [],
      }
    }
    const lines = citations.map((c, i) => `${i + 1}. ${c.title} (${c.sourceLabel}) → ${c.url}`)
    return {
      answer: [
        `Keyword search found ${hits.length} matching record(s) for “${query.trim()}”:`,
        ...lines,
      ].join('\n'),
      citations,
    }
  }

  return {
    searchKeyword,
    searchSemantic,
    askAi,
  }
}
