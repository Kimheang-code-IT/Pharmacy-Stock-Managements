export type ExportScope = 'all_matching' | 'current_page' | 'selected'

export interface ExportFieldOption {
  label: string
  value: string
}

export interface ExportRequest {
  startDate?: string
  endDate?: string
  scope: ExportScope
  fieldCodes: string[]
}

export type ExportJobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface ExportJob {
  id: string
  status: ExportJobStatus
  resource: string
  createdAt: string
  downloadUrl?: string
  expiresAt?: string
  error?: string
}

export interface CreateExportJobInput extends ExportRequest {
  resource: string
  query?: Record<string, unknown>
  selectedIds?: string[]
  format: 'csv'
}
