import type { ApiResponse, FieldOption } from '~/types/stock-pos/common'
import { CollectionEndpoints } from '~/utils/constants/api-endpoints'

const OPTIONS_CACHE_TTL_MS = 60_000
const optionsCache = new Map<string, {
  at: number
  data: FieldOption[]
  inflight?: Promise<FieldOption[]>
}>()

function optionsValueField(endpoint: string): 'id' | 'name' {
  try {
    const query = endpoint.includes('?') ? endpoint.slice(endpoint.indexOf('?') + 1) : ''
    const params = new URLSearchParams(query)
    return params.get('valueField') === 'name' ? 'name' : 'id'
  }
  catch {
    return 'id'
  }
}

function endpointPath(endpoint: string) {
  return endpoint.split('?')[0] || endpoint
}

function endpointParams(endpoint: string) {
  const query = endpoint.includes('?') ? endpoint.slice(endpoint.indexOf('?') + 1) : ''
  return new URLSearchParams(query)
}

/** Map an options endpoint (e.g. /api/v1/uoms/options) back to its collection name. */
function collectionFromEndpoint(endpoint: string): string | null {
  const path = endpointPath(endpoint).replace(/\/options$/, '')
  for (const [collection, value] of Object.entries(CollectionEndpoints)) {
    if (String(value) === path) return collection
  }
  return null
}

/**
 * Mock mode: resolve reference options from the in-memory entity repository
 * (active records only) instead of issuing real HTTP requests.
 */
async function loadMockReferenceOptions(endpoint: string): Promise<FieldOption[]> {
  const collection = collectionFromEndpoint(endpoint)
  if (!collection) return []
  const { useEntityRepository } = await import('~/repositories/index')
  const result = await useEntityRepository().list(collection, { status: 'Active', limit: 1000 })
  return result.items.map(row => ({
    label: String(row.name || row.displayName || row.label || row.code || row.id),
    value: String(row.id),
  })).filter(row => row.value)
}

export function useReferenceOptions() {
  const api = useApi()

  function isMockMode(): boolean {
    try {
      return useRuntimeConfig().public.useMockData === true
    }
    catch {
      return false
    }
  }

  async function loadReferenceOptionsUncached(endpoint: string, search = ''): Promise<FieldOption[]> {
    if (isMockMode()) return loadMockReferenceOptions(endpoint)

    const path = endpointPath(endpoint)
    const params = endpointParams(endpoint)
    const valueField = optionsValueField(endpoint)

    const response = await api.get<ApiResponse<FieldOption[]> | FieldOption[]>(path, {
      query: {
        q: search || undefined,
        limit: 50,
        status: 'active',
        valueField,
        hierarchy: params.get('hierarchy') || undefined,
        excludeId: params.get('excludeId') || undefined,
      },
      suppressErrorToast: true,
      requestKey: `field-options:${endpoint}`,
      cancelPrevious: true,
    })
    const rows = Array.isArray(response) ? response : response.data
    return (rows || []).map((row: FieldOption & { id?: string | number, name?: string }) => ({
      label: String(row.label ?? row.name ?? row.value ?? row.id ?? ''),
      value: String(row.value ?? row.id ?? ''),
    })).filter(row => row.value)
  }

  async function loadReferenceOptions(endpoint: string, search = '') {
    const cacheKey = `${endpoint}::${search}`
    if (!search) {
      const cached = optionsCache.get(cacheKey)
      if (cached?.inflight) return cached.inflight
      if (cached && Date.now() - cached.at < OPTIONS_CACHE_TTL_MS) return cached.data
    }

    const inflight = loadReferenceOptionsUncached(endpoint, search)
    if (!search) {
      optionsCache.set(cacheKey, { at: 0, data: [], inflight })
    }

    try {
      const data = await inflight
      if (!search) {
        optionsCache.set(cacheKey, { at: Date.now(), data })
      }
      return data
    }
    catch (error) {
      if (!search) optionsCache.delete(cacheKey)
      throw error
    }
  }

  return {
    loadReferenceOptions,
  }
}
