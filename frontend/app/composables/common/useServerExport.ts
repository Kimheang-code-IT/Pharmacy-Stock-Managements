import type { ExportRequest } from '~/types/stock-pos/export'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { getAccessToken } from '~/utils/auth/tokens'
import { isAutoApiBase, isSameOriginApiBase, resolveApiBase } from '~/utils/api/base-url'
import { useApi } from '~/composables/useApi'

const POLL_INTERVAL_MS = 2000
const MAX_POLL_ATTEMPTS = 60

interface ExportJobView {
  id: string
  status: string
  downloadUrl?: string | null
  error?: string | null
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * Server export pipeline for HTTP mode: create the job, poll to a terminal
 * state with bounded stopping conditions, then download the result.
 */
export function useServerExport() {
  const api = useApi()
  const config = useRuntimeConfig()
  const running = ref(false)
  const error = ref<string | null>(null)

  function getApiBase(): string {
    const configuredBase = String(config.public.apiBase || '')
    const requireSecureApi = import.meta.env.PROD
      && config.public.useMockData === false
      && !isAutoApiBase(configuredBase)
      && !isSameOriginApiBase(configuredBase)
    const resolved = resolveApiBase({
      configured: configuredBase,
      internalBase: String(config.apiInternalBase || ''),
      requireHttps: requireSecureApi,
    })
    if (!resolved) {
      throw new Error('Invalid API base URL. Production APIs must use HTTPS.')
    }
    return resolved
  }

  async function download(jobId: string, filename: string) {
    const response = await $fetch<Blob>(`${getApiBase()}${ApiEndpoints.EXPORT_DOWNLOAD(jobId)}`, {
      responseType: 'blob',
      headers: { Authorization: `Bearer ${getAccessToken() || ''}` },
    })
    saveBlob(response, filename)
  }

  async function request(resource: string, request: ExportRequest, filename?: string) {
    if (running.value) return
    running.value = true
    error.value = null
    try {
      const created = await api.post<{ data?: ExportJobView } | ExportJobView>(ApiEndpoints.EXPORTS, {
        resource,
        format: 'csv',
        scope: request.scope,
        fieldCodes: request.fieldCodes,
        startDate: request.startDate || null,
        endDate: request.endDate || null,
      })
      const job = ('data' in (created as object) && (created as { data?: ExportJobView }).data)
        ? (created as { data: ExportJobView }).data
        : created as ExportJobView

      let status = String(job?.status || 'queued')
      const jobId = String(job?.id || '')
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS && !['completed', 'failed'].includes(status); attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS))
        const view = await api.get<{ data?: ExportJobView } | ExportJobView>(ApiEndpoints.EXPORT(jobId), {
          suppressErrorToast: true,
          cancelPrevious: false,
        })
        const data = ('data' in (view as object) && (view as { data?: ExportJobView }).data)
          ? (view as { data: ExportJobView }).data
          : view as ExportJobView
        status = String(data?.status || status)
        if (status === 'failed') {
          throw new Error(String(data?.error || 'Export failed'))
        }
      }

      if (status !== 'completed') {
        throw new Error('Export timed out. Try a narrower date range.')
      }
      await download(jobId, filename || `${resource}-${new Date().toISOString().slice(0, 10)}.csv`)
    }
    catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    }
    finally {
      running.value = false
    }
  }

  return { request, running, error }
}
