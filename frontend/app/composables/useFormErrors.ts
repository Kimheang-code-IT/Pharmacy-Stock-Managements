import { getCurrentScope, onScopeDispose, reactive } from 'vue'
import { normalizeApiError } from '~/utils/api/errors'

/**
 * Shared form field-error store.
 *
 * The backend returns `{ detail: { message, field_errors: { key: message } } }`
 * for validation failures. `useApi` publishes those errors here (and skips its
 * generic toast) whenever at least one form is mounted, so each field can show
 * its own message inline instead of one opaque toast.
 *
 * Field keys come from two vocabularies: the backend uses snake_case
 * (`customer_id`, `paid_amount`) while form configs use camelCase
 * (`customerId`, `paidAmount`). Lookups try the exact key first, then both
 * normalized spellings.
 */
const fieldErrors = reactive<Record<string, string>>({})

/** Number of mounted forms that can display field errors inline. */
let sinkCount = 0

/** Field keys some mounted form can actually render (ref-counted). */
const claims = new Map<string, number>()

function toSnakeCase(key: string): string {
  return key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase()
}

function toCamelCase(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, char: string) => char.toUpperCase())
}

function existingKeys(): string[] {
  return Object.keys(fieldErrors)
}

/** Replace the published errors with a fresh set (empty clears them). */
export function publishFieldErrors(errors: Record<string, string>): void {
  for (const key of existingKeys()) Reflect.deleteProperty(fieldErrors, key)
  for (const [key, value] of Object.entries(errors)) {
    if (value) fieldErrors[key] = value
  }
}

export function clearPublishedFieldErrors(): void {
  publishFieldErrors({})
}

/** True while at least one form is mounted and can render inline errors. */
export function hasActiveFieldErrorSink(): boolean {
  return sinkCount > 0
}

function claimKey(key: string): void {
  claims.set(key, (claims.get(key) ?? 0) + 1)
}

function releaseKey(key: string): void {
  const next = (claims.get(key) ?? 0) - 1
  if (next <= 0) claims.delete(key)
  else claims.set(key, next)
}

/** True when some mounted field renders this key (any spelling). */
function isClaimed(key: string): boolean {
  return claims.has(key) || claims.has(toSnakeCase(key)) || claims.has(toCamelCase(key))
}

/**
 * True when at least one published error key has no matching mounted field, so
 * the generic toast must still fire instead of silently hiding the message.
 */
export function hasUnclaimedFieldError(errors: Record<string, string>): boolean {
  return Object.keys(errors).some(key => !isClaimed(key))
}

/** Look up a message by exact key, then snake_case / camelCase equivalents. */
export function fieldErrorFor(key: string): string | undefined {
  return fieldErrors[key]
    || fieldErrors[toSnakeCase(key)]
    || fieldErrors[toCamelCase(key)]
    || undefined
}

/** Read field errors off a thrown API error without publishing them. */
export function fieldErrorsFromError(error: unknown): Record<string, string> {
  if (!error || typeof error !== 'object') return {}
  const data = (error as { data?: unknown }).data
  if (data === undefined) return {}
  const status = (error as { statusCode?: number }).statusCode ?? 500
  return normalizeApiError(data, status).fieldErrors
}

/**
 * Composable used by forms: registers a sink while the form is mounted and
 * exposes the reactive errors + a per-field lookup.
 */
export function useFormErrors() {
  if (getCurrentScope()) {
    sinkCount += 1
    onScopeDispose(() => {
      sinkCount = Math.max(0, sinkCount - 1)
    })
  }

  return {
    errors: fieldErrors,
    errorFor: fieldErrorFor,
    clear: clearPublishedFieldErrors,
    /** Declare that this form renders `key`, so its error can be inline. */
    claim(key: string): void {
      if (getCurrentScope()) {
        claimKey(key)
        onScopeDispose(() => releaseKey(key))
      }
    },
    setFromError(error: unknown): Record<string, string> {
      const errors = fieldErrorsFromError(error)
      publishFieldErrors(errors)
      return errors
    },
  }
}
