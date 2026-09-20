/**
 * Batch lot display helpers (spec: batch/expiry + FEFO). Batch identity =
 * product + batch_no + expiry_date: the same batch number received with a
 * different expiry is a distinct lot. Batches without a batch no (unbatched
 * stock) are handled invisibly by the backend and are never shown as
 * selectable lots.
 */

/** Badge color for a batch status value (`app.stock.batch*` labels). */
export function batchStatusColor(status: unknown): 'success' | 'warning' | 'neutral' {
  const value = String(status ?? '')
  if (value === 'Expired') return 'warning'
  if (value === 'Depleted') return 'neutral'
  return 'success'
}
