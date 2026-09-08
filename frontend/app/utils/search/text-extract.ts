/**
 * Mock file-text extraction for Phase 2 indexing.
 * Real PDF/OCR parsers can replace extractText later.
 */

export type ExtractInput = {
  fileName: string
  mimeType?: string
  /** Optional known plain-text body (txt/csv uploads). */
  rawText?: string
  /** Entity title / context for seeded extracts. */
  contextTitle?: string
}

const MOCK_BODY_BY_EXT: Record<string, string> = {
  pdf: 'Official correspondence cover letter. Subject: administrative follow-up and document review. Please confirm receipt and route for approval.',
  doc: 'Internal memorandum describing process steps, responsible officers, and target completion dates for this record.',
  docx: 'Internal memorandum describing process steps, responsible officers, and target completion dates for this record.',
  xls: 'Spreadsheet summary of line items, amounts, departments, and status codes related to this upload.',
  xlsx: 'Spreadsheet summary of line items, amounts, departments, and status codes related to this upload.',
  csv: 'id,department,status,updated_at\n1,MEF,active,2026-01-15\n2,GDT,pending,2026-02-01',
  txt: 'Plain text note attached to this record for operational tracking and search indexing.',
  zip: 'Archive containing supporting documents, scanned forms, and annex files for this submission.',
  png: 'Image attachment (scan or screenshot). Alt context for search indexing only.',
  jpg: 'Image attachment (scan or screenshot). Alt context for search indexing only.',
  jpeg: 'Image attachment (scan or screenshot). Alt context for search indexing only.',
}

function extensionOf(fileName: string): string {
  const parts = fileName.toLowerCase().split('.')
  return parts.length > 1 ? parts[parts.length - 1]! : ''
}

/**
 * Returns searchable plain text for an uploaded/linked file.
 */
export function extractText(input: ExtractInput): string {
  const name = String(input.fileName || 'file').trim()
  const ext = extensionOf(name)
  const mime = (input.mimeType || '').toLowerCase()

  if (input.rawText && input.rawText.trim()) {
    return `${name}\n${input.rawText.trim()}`
  }

  if (mime.startsWith('text/') || ext === 'txt' || ext === 'csv' || ext === 'md') {
    const body = MOCK_BODY_BY_EXT[ext] || MOCK_BODY_BY_EXT.txt!
    return `${name}\n${body}`
  }

  const seeded = MOCK_BODY_BY_EXT[ext]
    || (mime.includes('pdf') ? MOCK_BODY_BY_EXT.pdf
      : mime.includes('word') ? MOCK_BODY_BY_EXT.docx
        : mime.includes('sheet') || mime.includes('excel') ? MOCK_BODY_BY_EXT.xlsx
          : mime.startsWith('image/') ? MOCK_BODY_BY_EXT.png
            : 'Supporting file content available for operational search after indexing.')

  const context = input.contextTitle ? `Related to: ${input.contextTitle}.` : ''
  return [name, context, seeded].filter(Boolean).join('\n')
}

/** Build a short snippet around the first query match. */
export function makeSnippet(text: string, query: string, radius = 72): string {
  const body = text.replace(/\s+/g, ' ').trim()
  if (!body) return ''
  const q = query.trim().toLowerCase()
  if (!q) return body.slice(0, radius * 2) + (body.length > radius * 2 ? '…' : '')

  const lower = body.toLowerCase()
  const idx = lower.indexOf(q)
  if (idx < 0) return body.slice(0, radius * 2) + (body.length > radius * 2 ? '…' : '')

  const start = Math.max(0, idx - radius)
  const end = Math.min(body.length, idx + q.length + radius)
  const prefix = start > 0 ? '…' : ''
  const suffix = end < body.length ? '…' : ''
  return `${prefix}${body.slice(start, end)}${suffix}`
}
