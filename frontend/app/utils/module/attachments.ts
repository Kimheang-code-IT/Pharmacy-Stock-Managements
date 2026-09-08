import { useSettingsRepositories } from '~/repositories'
import { createClientId } from '~/utils/client-id'
import { extractText } from '~/utils/search/text-extract'
import { safeExternalUrl, safeFilePreviewUrl } from '~/utils/security/url'

const MIME_BY_EXT: Record<string, string> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  svg: 'image/svg+xml',
  txt: 'text/plain',
  md: 'text/plain',
  csv: 'text/csv',
  html: 'text/html',
  json: 'application/json',
  mp4: 'video/mp4',
  webm: 'video/webm',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
}

const SAFE_SOURCE_PREVIEW_MIMES = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'text/plain',
  'text/csv',
])

type PreviewCacheEntry = { url: string }

const previewCache = new Map<string, PreviewCacheEntry>()

function extensionOf(fileName: string) {
  const parts = fileName.toLowerCase().split('.')
  return parts.length > 1 ? parts[parts.length - 1]! : ''
}

export function mimeFromFileName(fileName: string, mimeType = '') {
  const mime = String(mimeType || '').trim()
  if (mime) return mime
  return MIME_BY_EXT[extensionOf(fileName)] || 'application/octet-stream'
}

export function attachmentRowFromFile(file: File, uploadedBy: string, uploadedAt = new Date().toISOString()) {
  const previewKey = createClientId('file')
  const mimeType = mimeFromFileName(file.name, file.type)
  if (SAFE_SOURCE_PREVIEW_MIMES.has(mimeType)) rememberFilePreview(previewKey, file)
  return {
    fileName: file.name,
    file: file.name,
    uploadedBy,
    uploadedAt,
    uploadDate: uploadedAt.slice(0, 10),
    mimeType,
    fileSize: file.size,
    previewKey,
  }
}

export function fileTableRowName(row: Record<string, unknown>) {
  return String(row.fileName || row.file || row.documentNo || '').trim()
}

export function fileTableRowBy(row: Record<string, unknown>) {
  return String(row.uploadedBy || row.createdBy || '').trim()
}

export function fileTableRowCreated(row: Record<string, unknown>) {
  return String(row.uploadedAt || row.uploadDate || row.createdAt || '').trim()
}

/** Job Files tab uses the same attachment rows as quotations. Fall back to related documents. */
export function jobFileAttachments(
  job: Record<string, unknown>,
  documents: Array<Record<string, unknown>> = [],
) {
  const stored = Array.isArray(job.attachments) ? job.attachments : []
  if (stored.length) return stored as Array<Record<string, unknown>>
  return documents.map((row) => {
    const fileName = fileTableRowName(row)
    return {
      fileName,
      file: fileName,
      uploadedBy: fileTableRowBy(row),
      uploadedAt: fileTableRowCreated(row),
      mimeType: mimeFromFileName(fileName, String(row.mimeType || '')),
      fileSize: row.fileSize,
    }
  })
}

function canCreateObjectUrl() {
  return typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function'
}

function rememberFilePreview(key: string, source: Blob) {
  if (!canCreateObjectUrl()) return
  const previous = previewCache.get(key)
  if (previous) URL.revokeObjectURL(previous.url)
  previewCache.set(key, { url: URL.createObjectURL(source) })
}

function cacheKeyFor(row: Record<string, unknown>) {
  const previewKey = String(row.previewKey || '').trim()
  if (previewKey) return previewKey
  return `mock:${fileTableRowName(row)}:${fileTableRowCreated(row)}`
}

function pdfEscape(value: string) {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)')
    .replace(/[^\x20-\x7E]/g, '?')
}

function htmlEscape(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Minimal PDF so the browser’s native PDF viewer can open seeded mock files. */
export function mockPdfBytes(title: string, body: string) {
  const heading = pdfEscape(title.slice(0, 90))
  const line = pdfEscape(body.replace(/\s+/g, ' ').slice(0, 220))
  const content = `BT /F1 16 Tf 48 740 Td (${heading}) Tj 0 -26 Td /F1 11 Tf (${line}) Tj ET`
  const objects = [
    '1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n',
    '2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n',
    '3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n',
    `4 0 obj << /Length ${content.length} >> stream\n${content}\nendstream\nendobj\n`,
    '5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n',
  ]
  let offset = '%PDF-1.4\n'.length
  const offsets = [0]
  let pdf = '%PDF-1.4\n'
  for (const object of objects) {
    offsets.push(offset)
    pdf += object
    offset += object.length
  }
  let xref = 'xref\n0 6\n0000000000 65535 f \n'
  for (let index = 1; index <= 5; index++) {
    xref += `${String(offsets[index]).padStart(10, '0')} 00000 n \n`
  }
  return `${pdf}${xref}trailer << /Size 6 /Root 1 0 R >>\nstartxref\n${offset}\n%%EOF\n`
}

export function filePreviewBlob(row: Record<string, unknown>): Blob | null {
  const name = fileTableRowName(row)
  if (!name) return null
  const mime = mimeFromFileName(name, String(row.mimeType || ''))
  const body = extractText({ fileName: name, mimeType: mime })
  const ext = extensionOf(name)

  if (mime === 'application/pdf' || ext === 'pdf') {
    return new Blob([mockPdfBytes(name, body)], { type: 'application/pdf' })
  }
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) {
    const svg = `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640"><rect fill="#f8fafc" width="960" height="640"/><rect x="48" y="48" width="864" height="544" fill="#fff" stroke="#e2e8f0"/><text x="80" y="140" font-family="sans-serif" font-size="28" fill="#0f172a">${htmlEscape(name)}</text><text x="80" y="190" font-family="sans-serif" font-size="16" fill="#64748b">${htmlEscape(body.slice(0, 180))}</text></svg>`
    return new Blob([svg], { type: 'image/svg+xml' })
  }
  if (mime.startsWith('text/') || ['txt', 'csv', 'md', 'json'].includes(ext)) {
    return new Blob([body], { type: mime.startsWith('text/') ? mime : 'text/plain' })
  }
  const html = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>${htmlEscape(name)}</title><style>body{font-family:system-ui,sans-serif;margin:2rem;color:#0f172a}pre{white-space:pre-wrap}</style></head><body><h1>${htmlEscape(name)}</h1><pre>${htmlEscape(body)}</pre></body></html>`
  return new Blob([html], { type: 'text/html' })
}

/** Object URL or http(s) URL for a native browser-tab preview. */
export function filePreviewHref(row: Record<string, unknown>): string | null {
  const persisted = safeExternalUrl(row.url || row.fileUrl || row.href)
  if (persisted) return persisted
  const storedPreview = safeFilePreviewUrl(row.previewUrl)
  if (storedPreview && !storedPreview.startsWith('blob:')) return storedPreview
  if (!canCreateObjectUrl()) return null
  const key = cacheKeyFor(row)
  const cached = previewCache.get(key)
  if (cached) return cached.url
  const blob = filePreviewBlob(row)
  if (!blob) return null
  rememberFilePreview(key, blob)
  return previewCache.get(key)?.url || null
}

export function revokeFilePreview(row: Record<string, unknown>) {
  const key = String(row.previewKey || '').trim()
  if (!key) return
  const cached = previewCache.get(key)
  if (!cached) return
  if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(cached.url)
  previewCache.delete(key)
}

export function useFileAttachments() {
  const inputRef = ref<HTMLInputElement | null>(null)
  const auth = useAuthStore()
  const toast = useToast()
  const { t } = useI18n()
  const { appConfig } = useSettingsRepositories()
  const maxMb = useState('max-upload-size-mb', () => 50)

  onMounted(async () => {
    try {
      const config = await appConfig.get()
      const next = Number(config.general?.maxUploadSizeMb)
      if (Number.isFinite(next) && next > 0) maxMb.value = next
    }
    catch {
      /* keep default */
    }
  })

  function openPicker() {
    inputRef.value?.click()
  }

  function rowsFromInput(event: Event) {
    const input = event.target as HTMLInputElement
    const files = Array.from(input.files || [])
    input.value = ''
    const uploadedBy = String(auth.user?.name || t('app.ui.currentUser'))
    const uploadedAt = new Date().toISOString()
    const accepted: Array<Record<string, unknown>> = []
    for (const file of files) {
      if (file.size > maxMb.value * 1024 * 1024) {
        toast.add({ title: t('app.ui.fileTooLarge', { size: maxMb.value }), description: file.name, color: 'error' })
        continue
      }
      accepted.push(attachmentRowFromFile(file, uploadedBy, uploadedAt))
    }
    if (accepted.length) toast.add({ title: t('app.ui.fileUploaded'), color: 'success' })
    return accepted
  }

  return { inputRef, openPicker, rowsFromInput }
}
