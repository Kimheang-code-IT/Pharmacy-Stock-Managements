/**
 * Central normalization of FastAPI error payloads.
 *
 * Backend errors look like:
 *   { detail: { code, message, field_errors? } }
 * Ordinary FastAPI validation errors look like:
 *   { detail: Array<{ msg, loc, type }> } or { detail: string }
 */

export interface NormalizedApiError {
  statusCode: number
  code: string
  message: string
  fieldErrors: Record<string, string>
  payload: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function normalizeApiError(payload: unknown, statusCode = 500): NormalizedApiError {
  const detail = isRecord(payload) ? payload.detail : undefined

  if (isRecord(detail)) {
    const fieldErrors: Record<string, string> = {}
    const rawFieldErrors = detail.field_errors
    if (isRecord(rawFieldErrors)) {
      for (const [key, value] of Object.entries(rawFieldErrors)) {
        fieldErrors[key] = String(value)
      }
    }
    return {
      statusCode,
      code: String(detail.code || 'ERROR'),
      message: String(detail.message || 'Request failed'),
      fieldErrors,
      payload,
    }
  }

  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (isRecord(item)) {
        const loc = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join('.') : ''
        const msg = String(item.msg || 'Invalid value')
        return loc ? `${loc}: ${msg}` : msg
      }
      return String(item)
    })
    const fieldErrors: Record<string, string> = {}
    for (const item of detail) {
      if (isRecord(item) && Array.isArray(item.loc) && item.loc.length > 1) {
        fieldErrors[String(item.loc.at(-1))] = String(item.msg || 'Invalid value')
      }
    }
    return {
      statusCode,
      code: 'VALIDATION_ERROR',
      message: parts.join('; ') || 'Validation failed',
      fieldErrors,
      payload,
    }
  }

  if (typeof detail === 'string' && detail.trim()) {
    return { statusCode, code: 'ERROR', message: detail, fieldErrors: {}, payload }
  }

  if (isRecord(payload) && typeof payload.message === 'string' && payload.message.trim()) {
    return { statusCode, code: 'ERROR', message: payload.message, fieldErrors: {}, payload }
  }

  return {
    statusCode,
    code: 'ERROR',
    message: 'Something went wrong. Please try again.',
    fieldErrors: {},
    payload,
  }
}
