export interface PersonSummary {
  id: string
  name: string
  email?: string
  avatarUrl?: string
}

export interface ApiMeta {
  page: number
  limit: number
  total: number
  totalPages?: number
  cursor?: string | null
  nextCursor?: string | null
}

export interface ApiErrorItem {
  code: string
  message: string
  field?: string
}

export interface ApiResponse<T> {
  data: T
  meta?: ApiMeta
  errors?: ApiErrorItem[]
}

export interface ListQuery {
  q?: string
  page?: number
  limit?: number
  sort?: string
  status?: string
  startDate?: string
  endDate?: string
  [key: string]: string | number | boolean | undefined
}

export interface AttachmentMeta {
  id: string
  name: string
  mimeType: string
  sizeBytes: number
  url?: string
  uploadedBy?: PersonSummary
  uploadedAt: string
  storageSource?: 'local'
}

export type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'date'
  | 'datetime'
  | 'select'
  | 'multiselect'
  | 'boolean'
  | 'file'
  | 'url'
  | 'permission-matrix'
  | 'secret'
  | 'color'
  | 'image'
  | 'csv-list'
  | 'notification-rules'
  | 'connection-status'
  | 'alert'
  | 'icon'
  | 'line-table'
  | 'related-records'
  | 'uom-conversions'

export interface FieldOption {
  label?: string
  value: string
  labelKey?: string
  meta?: Record<string, unknown>
}

export interface ConnectionStatusFieldValue {
  status: string
  message?: string
  lastTestedAt?: string
  details?: Array<{ label: string, value: string }>
}

export interface DocumentFieldSchema {
  key: string
  labelKey: string
  label?: string
  type: FieldType
  required?: boolean
  readOnly?: boolean
  colSpan?: 1 | 2
  options?: FieldOption[]
  optionsEndpoint?: string
  helpKey?: string
  help?: string
  hintKey?: string
  placeholderKey?: string
  placeholder?: string
  rows?: number
  alertColor?: 'error' | 'warning' | 'info' | 'success' | 'neutral'
  meta?: Record<string, unknown>
}

export interface DocumentSectionSchema {
  id: string
  titleKey?: string
  title?: string
  descriptionKey?: string
  description?: string
  fields: DocumentFieldSchema[]
}

export interface DocumentTabSchema {
  id: string
  labelKey: string
  label?: string
  sections: DocumentSectionSchema[]
}
