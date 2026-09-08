/** Temporary identity for unsaved client-side form rows; never used as a server record ID. */
export function createClientId(prefix = 'row'): string {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${globalThis.crypto.randomUUID()}`
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}
