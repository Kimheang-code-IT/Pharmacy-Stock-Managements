/**
 * Shared control styling for App*Field components.
 * - Full width of the parent form/dialog by default
 * - Idle: soft fill, no hard border (handled by the global `soft` input variant)
 * - Error: soft error fill + error ring/border
 */
export function fieldControlClass(error?: boolean): string {
  return error
    ? 'w-full ring-2 ring-inset ring-error bg-error/5'
    : 'w-full'
}
