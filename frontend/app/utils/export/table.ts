import type { ExportFormat } from '~/types/stock-pos/export'
import { resolveApiBase } from '~/utils/api/base-url'
import { getAccessToken } from '~/utils/auth/tokens'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { configuredNumberFormat } from '~/utils/format/format-service'

/**
 * Download a page's table as Excel or PDF. The rows are rendered by the Python
 * backend (openpyxl / reportlab) and streamed back as a file attachment, so the
 * browser saves it straight to the computer's drive — nothing to install.
 */
export type ExportColumnType = 'text' | 'number' | 'money' | 'date'

export interface ExportTableColumn {
  key: string
  label: string
  /** Drives PDF alignment, Excel formats and the totals row. */
  type?: ExportColumnType
}

export interface ExportTableInput {
  title: string
  format: ExportFormat
  columns: ExportTableColumn[]
  rows: Array<Record<string, unknown>>
  subtitle?: string | null
}

function exportBaseUrl(): string {
  const config = useRuntimeConfig()
  const base = resolveApiBase({
    configured: String(config.public.apiBase || ''),
    internalBase: import.meta.server ? String(config.apiInternalBase || '') : undefined,
  })
  if (!base) throw new Error('Invalid API base URL.')
  return base
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header)
  return match?.[1] ? decodeURIComponent(match[1]) : fallback
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function downloadTableExport(input: ExportTableInput): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(`${exportBaseUrl()}${ApiEndpoints.EXPORT_TABLE}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/octet-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      title: input.title,
      format: input.format,
      numberFormat: configuredNumberFormat(),
      subtitle: input.subtitle ?? null,
      columns: input.columns,
      rows: input.rows,
    }),
  })

  if (!response.ok) {
    let message = `Export failed (${response.status})`
    try {
      const data = await response.json() as { detail?: { message?: string } | string }
      message = (typeof data?.detail === 'object' ? data.detail?.message : data?.detail) || message
    }
    catch {
      // Non-JSON error body — keep the status message.
    }
    throw new Error(String(message))
  }

  const blob = await response.blob()
  triggerDownload(
    blob,
    filenameFromDisposition(response.headers.get('content-disposition'), `${input.title}.${input.format}`),
  )
}
