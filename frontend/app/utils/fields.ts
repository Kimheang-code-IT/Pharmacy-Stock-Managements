/**
 * Shared control styling for App*Field components.
 * - Idle: soft fill, no hard border (handled by the global `soft` input variant)
 * - Error: soft error fill + error ring/border
 */
export function fieldControlClass(error?: boolean): string {
  return error
    ? 'ring-2 ring-inset ring-error bg-error/5'
    : ''
}
