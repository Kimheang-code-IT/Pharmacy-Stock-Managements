/**
 * Shared Nuxt UI styles for toolbar / dashboard filter pills and live search.
 * Active border uses default grey (`ring-default`), not inverted/black.
 */

import type { AppFontSize } from '~/types/stock-pos/settings'

const selectChrome = 'rounded-sm bg-elevated/70 font-medium text-highlighted'
const selectIdle = `${selectChrome} ring-0`
const selectActive = `${selectChrome} ring-1 ring-inset ring-default`

export const filterSelectUi = {
  base: selectIdle,
  value: 'truncate',
  trailingIcon: 'text-muted',
  content: 'max-h-60 min-w-(--reka-combobox-trigger-width)',
} as const

export function getFilterSelectUi(active: boolean) {
  return {
    ...filterSelectUi,
    base: active ? selectActive : selectIdle,
  }
}

export function getFilterSearchUi(active: boolean) {
  return {
    base: active
      ? 'rounded-sm bg-elevated/70 ring-1 ring-inset ring-default'
      : 'rounded-sm bg-elevated/70 ring-0 focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-default',
  }
}

export function getFilterDateUi(
  active: boolean,
  options?: {
    isDateTime?: boolean
    isRange?: boolean
    fitContent?: boolean
    fullWidth?: boolean
    fontSize?: AppFontSize
  },
) {
  const fontSize = options?.fontSize ?? 'md'

  const chrome = active
    ? 'rounded-sm bg-elevated/70 ring-1 ring-inset ring-default'
    : 'rounded-sm bg-elevated/70 ring-0 has-focus:ring-1 has-focus:ring-inset has-focus:ring-default'

  const segment = options?.isDateTime
    ? [
        'data-[segment=hour]:min-w-7',
        'data-[segment=minute]:min-w-7',
        'data-[segment=dayPeriod]:min-w-8',
        fontSize === 'lg' || fontSize === 'xl' ? 'data-[segment=day]:w-9 data-[segment=month]:w-9 data-[segment=year]:w-11' : '',
      ].filter(Boolean).join(' ')
    : undefined

  const trailingEnd = options?.isDateTime && options?.isRange
    ? fontSize === 'xl' ? 'pe-12' : fontSize === 'lg' ? 'pe-11' : 'pe-11'
    : options?.isDateTime
      ? fontSize === 'xl' ? 'pe-10' : 'pe-9'
      : options?.isRange
        ? 'pe-9'
        : 'pe-8'

  const rangeMinWidth = fontSize === 'xl'
    ? 'min-w-120'
    : fontSize === 'lg'
      ? 'min-w-112'
      : fontSize === 'sm'
        ? 'min-w-96'
        : 'min-w-104'

  const minWidth = options?.fullWidth
    ? 'w-full min-w-0'
    : options?.fitContent && options?.isDateTime && options?.isRange
      ? `w-auto ${rangeMinWidth} max-w-full`
      : options?.fitContent
        ? 'w-auto max-w-full'
        : 'w-full min-w-0'

  const width = `${minWidth} ${trailingEnd}`

  return {
    base: `${chrome} ${width}`,
    segment,
    trailing: 'pe-0.5',
    trailingIcon: 'text-muted',
  }
}

export function isFilterValueActive(value: unknown): boolean {
  if (value == null || value === '') return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'string') return value.trim().length > 0
  return true
}

/** Shared search box config for USelectMenu / filter dropdowns. */
export function getFilterSearchInputConfig(
  t: (key: string) => string,
  placeholderKey = 'components.filterSearch',
) {
  return {
    placeholder: t(placeholderKey),
    icon: 'i-lucide-search',
    type: 'text' as const,
    autocomplete: 'off',
    class: 'app-live-search',
  }
}
