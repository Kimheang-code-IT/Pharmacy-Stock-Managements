import type { AppBranding, AppInfo } from '~/types/stock-pos/settings'

const DEFAULT_PRIMARY = '#e8472a'

function isHexColor(value: string | undefined | null): value is string {
  return Boolean(value && /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value.trim()))
}

/** Expand a 3-digit hex (#f00) to 6-digit (#ff0000). */
function expandHex(hex: string): string {
  const h = hex.replace('#', '')
  if (h.length === 3) {
    return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`
  }
  return `#${h}`
}

function mixHex(hex: string, toward: 'white' | 'black', amount: number): string {
  const raw = expandHex(hex).slice(1)
  const r = Number.parseInt(raw.slice(0, 2), 16)
  const g = Number.parseInt(raw.slice(2, 4), 16)
  const b = Number.parseInt(raw.slice(4, 6), 16)
  const t = toward === 'white' ? 255 : 0
  const mix = (c: number) => Math.round(c + (t - c) * amount)
  const to = (c: number) => c.toString(16).padStart(2, '0')
  return `#${to(mix(r))}${to(mix(g))}${to(mix(b))}`
}

/**
 * Apply App Info primary color to the whole UI.
 * Font size is a per-user preference (see usePreferencesStore / user menu).
 */
export function useAppBranding() {
  function applyBranding(input?: Partial<AppBranding> | null) {
    if (!import.meta.client) return

    const root = document.documentElement
    const primary = isHexColor(input?.primaryColor)
      ? expandHex(input.primaryColor.trim())
      : DEFAULT_PRIMARY

    root.style.setProperty('--color-brand-50', mixHex(primary, 'white', 0.92))
    root.style.setProperty('--color-brand-100', mixHex(primary, 'white', 0.84))
    root.style.setProperty('--color-brand-200', mixHex(primary, 'white', 0.7))
    root.style.setProperty('--color-brand-300', mixHex(primary, 'white', 0.5))
    root.style.setProperty('--color-brand-400', mixHex(primary, 'white', 0.25))
    root.style.setProperty('--color-brand-500', primary)
    root.style.setProperty('--color-brand-600', mixHex(primary, 'black', 0.12))
    root.style.setProperty('--color-brand-700', mixHex(primary, 'black', 0.24))
    root.style.setProperty('--color-brand-800', mixHex(primary, 'black', 0.36))
    root.style.setProperty('--color-brand-900', mixHex(primary, 'black', 0.48))
    root.style.setProperty('--color-brand-950', mixHex(primary, 'black', 0.65))
  }

  function applyFromAppInfo(info: AppInfo | null | undefined) {
    applyBranding(info?.branding)
  }

  return {
    applyBranding,
    applyFromAppInfo,
  }
}
