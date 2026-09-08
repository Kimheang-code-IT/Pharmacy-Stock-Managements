import { defineStore } from 'pinia'
import { appModules, type ModuleConfig } from '~/config/modules'
import type { AppRecord } from '~/config/admin-seed'
import type { ApiMeta } from '~/types/stock-pos/common'
import type { EntityListQuery } from '~/repositories/contracts/entities'
import { useEntityRepository } from '~/repositories/index'
import { isApiCollection } from '~/utils/constants/api-endpoints'
import { documentSequencePreview, normalizeDocumentSequenceRecord } from '~/utils/document-sequences'
import { matchesFilter, parseFilterQuery } from '~/utils/filter/values'
import { normalizeAuditLog } from '~/utils/module/audit-logs'

export const useAppDataStore = defineStore('app-data', () => {
  const entityRepository = useEntityRepository()
  const revision = ref(0)
  const remoteCache = ref<Record<string, AppRecord[]>>({})
  const remoteMeta = ref<Record<string, ApiMeta | null>>({})
  const loadingCollections = ref<Record<string, boolean>>({})
  const collectionErrors = ref<Record<string, string | null>>({})

  // True only when the repository layer is the real /api/v1 HTTP adapter.
  // Mock mode (NUXT_PUBLIC_USE_MOCK_DATA=true) also loads through the same
  // EntityRepository (in-memory), so loading/error state is driven by the
  // repository — not by this flag. Never hardcode a mode here.
  const isHttpMode = (() => {
    try {
      return useRuntimeConfig().public.useMockData !== true
    }
    catch {
      // Outside a Nuxt context (tests/tooling): keep the repository-driven path.
      return true
    }
  })()

  function reload() {
    void reloadCollections(Object.keys(remoteCache.value))
  }

  function moduleByPath(path: string) {
    return appModules.find(module => module.path === path)
  }

  function decorate(collection: string, rows: AppRecord[]): AppRecord[] {
    if (collection === 'documentSequences') {
      return rows.map(row => ({
        ...normalizeDocumentSequenceRecord(row),
        nextNumberPreview: documentSequencePreview(row),
      }))
    }
    return rows
  }

  function list(collection: string): AppRecord[] {
    return decorate(collection, remoteCache.value[collection] || [])
  }

  function listMeta(collection: string): ApiMeta | null {
    return remoteMeta.value[collection] || null
  }

  function isLoading(collection: string): boolean {
    return Boolean(loadingCollections.value[collection])
  }

  function collectionError(collection: string): string | null {
    return collectionErrors.value[collection] || null
  }

  function get(collection: string, id: string) {
    return list(collection).find(row => String(row.id) === String(id)) || null
  }

  async function fetchList(collection: string, query: EntityListQuery = {}): Promise<AppRecord[]> {
    if (!isApiCollection(collection)) return []
    loadingCollections.value = { ...loadingCollections.value, [collection]: true }
    collectionErrors.value = { ...collectionErrors.value, [collection]: null }
    try {
      const result = await entityRepository.list(collection, query)
      remoteCache.value = { ...remoteCache.value, [collection]: result.items }
      remoteMeta.value = { ...remoteMeta.value, [collection]: result.meta }
      revision.value += 1
      return result.items
    }
    catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error)
      collectionErrors.value = { ...collectionErrors.value, [collection]: message }
      return []
    }
    finally {
      loadingCollections.value = { ...loadingCollections.value, [collection]: false }
    }
  }

  async function reloadCollection(collection: string) {
    return fetchList(collection)
  }

  async function reloadCollections(collections: string[]) {
    await Promise.all(collections.map(collection => fetchList(collection)))
  }

  async function fetchOne(collection: string, id: string): Promise<AppRecord | null> {
    if (!isApiCollection(collection)) return get(collection, id)
    try {
      const record = await entityRepository.get(collection, id)
      if (record) {
        const rows = remoteCache.value[collection] || []
        const index = rows.findIndex(row => String(row.id) === String(id))
        const next = index >= 0 ? rows.map((row, i) => i === index ? record : row) : [record, ...rows]
        remoteCache.value = { ...remoteCache.value, [collection]: next }
        revision.value += 1
      }
      return record
    }
    catch {
      return null
    }
  }

  async function createRemote(collection: string, input: Record<string, unknown>): Promise<AppRecord> {
    const created = await entityRepository.create(collection, input)
    const rows = remoteCache.value[collection] || []
    remoteCache.value = { ...remoteCache.value, [collection]: [created, ...rows.filter(row => String(row.id) !== String(created.id))] }
    revision.value += 1
    return created
  }

  async function updateRemote(collection: string, id: string, input: Record<string, unknown>): Promise<AppRecord> {
    const updated = await entityRepository.update(collection, id, input)
    const rows = remoteCache.value[collection] || []
    const index = rows.findIndex(row => String(row.id) === String(id))
    const next = index >= 0 ? rows.map((row, i) => i === index ? updated : row) : [updated, ...rows]
    remoteCache.value = { ...remoteCache.value, [collection]: next }
    revision.value += 1
    return updated
  }

  async function deleteRemote(collection: string, ids: string[]): Promise<void> {
    for (const id of ids) {
      await entityRepository.remove(collection, id)
    }
    const rows = remoteCache.value[collection] || []
    remoteCache.value = { ...remoteCache.value, [collection]: rows.filter(row => !ids.includes(String(row.id))) }
    revision.value += 1
  }

  async function setStatusRemote(collection: string, id: string, status: string): Promise<AppRecord> {
    if (!entityRepository.setStatus) throw new Error(`Status updates are not supported for ${collection}`)
    const updated = await entityRepository.setStatus(collection, id, status)
    const rows = remoteCache.value[collection] || []
    const index = rows.findIndex(row => String(row.id) === String(id))
    const next = index >= 0 ? rows.map((row, i) => i === index ? updated : row) : [updated, ...rows]
    remoteCache.value = { ...remoteCache.value, [collection]: next }
    revision.value += 1
    return updated
  }

  function query(module: ModuleConfig, options: {
    q?: string
    filters?: Record<string, string | string[]>
    page?: number
    limit?: number
    paginate?: boolean
    dateField?: string
    dateFrom?: string
    dateTo?: string
    sortKey?: string
    sortDir?: 'asc' | 'desc'
  }) {
    const q = (options.q || '').trim().toLowerCase()
    const filters = options.filters || {}
    let rows = list(module.collection)
    if (module.collection === 'auditLogs') rows = rows.map(normalizeAuditLog)
    if (q) {
      rows = rows.filter(row => Object.values(row).some(value => String(value ?? '').toLowerCase().includes(q)))
    }
    for (const [key, value] of Object.entries(filters)) {
      if (!parseFilterQuery(value).length) continue
      rows = rows.filter(row => matchesFilter(row[key], value))
    }
    const dateField = options.dateField
    const dateFrom = (options.dateFrom || '').slice(0, 10)
    const dateTo = (options.dateTo || '').slice(0, 10)
    if (dateField && (dateFrom || dateTo)) {
      rows = rows.filter((row) => {
        const day = String(row[dateField] ?? '').slice(0, 10)
        if (!day) return false
        if (dateFrom && day < dateFrom) return false
        if (dateTo && day > dateTo) return false
        return true
      })
    }
    if (options.sortKey && options.sortDir) {
      const dir = options.sortDir === 'desc' ? -1 : 1
      const sortKey = options.sortKey
      rows = [...rows].sort((a, b) => String(a[sortKey] ?? '').localeCompare(String(b[sortKey] ?? ''), undefined, { numeric: true }) * dir)
    }
    const page = options.page || 1
    const limit = options.limit || 10
    const start = (page - 1) * limit
    const meta = listMeta(module.collection)
    const clientNarrowed = Boolean(q) || Object.keys(filters).length > 0 || Boolean(dateField && (dateFrom || dateTo))
    const total = meta && !clientNarrowed ? meta.total : rows.length
    return {
      rows: options.paginate === false ? rows : rows.slice(start, start + limit),
      total,
      all: rows,
    }
  }

  function related(module: ModuleConfig, record: AppRecord) {
    return (module.related || []).map((item) => {
      const target = moduleByPath(item.path)
      const rows = target ? list(target.collection).filter(row => String(row[item.foreignKey] ?? '') === String(record[item.localKey] ?? '')) : []
      return { ...item, rows, module: target }
    })
  }

  return {
    collections: computed(() => remoteCache.value),
    isHttpMode,
    reload,
    list,
    listMeta,
    isLoading,
    collectionError,
    get,
    query,
    related,
    fetchList,
    fetchOne,
    createRemote,
    updateRemote,
    deleteRemote,
    setStatusRemote,
    reloadCollection,
    reloadCollections,
  }
})
