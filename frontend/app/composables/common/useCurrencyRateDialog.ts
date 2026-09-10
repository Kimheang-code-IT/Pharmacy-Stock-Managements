import type { Ref } from 'vue'

/**
 * Shared USD/KHR toggle logic for every price-field currency toggle.
 *
 * A document records all of its amounts in ONE currency, so toggling a
 * price field switches the whole document. KHR amounts are meaningless
 * without a rate, therefore switching to KHR opens the shared exchange-
 * rate dialog first (1 USD = ? KHR). Confirming applies the rate;
 * cancelling keeps the previous currency, so a KHR document can never be
 * recorded without a rate.
 *
 * Consumers own the currency/rate state (refs or writable computeds
 * backed by their form model) and render `<CommonAppExchangeRateDialog>`
 * with the returned `dialogOpen` / `confirm`.
 */
export function useCurrencyRateDialog(state: {
  currency: Ref<'USD' | 'KHR'>
  /** Exchange rate (KHR per 1 USD); set on confirm, cleared for USD. */
  rate: Ref<number | undefined>
  /** Extra side effects once the currency actually changed (e.g. clear debt selection). */
  onChanged?: (value: 'USD' | 'KHR') => void
}) {
  const dialogOpen = ref(false)

  function apply(value: 'USD' | 'KHR', rate?: number) {
    state.currency.value = value
    state.onChanged?.(value)
    state.rate.value = value === 'KHR' ? rate : undefined
  }

  /** Toggle handler for the USD/KHR buttons on price fields. */
  function toggle(value: 'USD' | 'KHR') {
    if (value === state.currency.value) return
    if (value === 'USD' || Number(state.rate.value || 0) > 0) {
      apply(value, value === 'KHR' ? state.rate.value : undefined)
      return
    }
    // KHR without a known rate → ask through the shared dialog.
    dialogOpen.value = true
  }

  /** Dialog confirmed: record the rate and switch to KHR. */
  function confirm(rate: number) {
    const parsed = Number(rate)
    if (!Number.isFinite(parsed) || parsed <= 0) return
    apply('KHR', parsed)
  }

  return { dialogOpen, toggle, confirm }
}
