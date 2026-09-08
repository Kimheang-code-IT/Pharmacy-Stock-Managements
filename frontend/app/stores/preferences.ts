import { defineStore } from 'pinia'
import { computed } from 'vue'
import type { AppFontSize } from '~/types/stock-pos/settings'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

const THEME_PRIMARY_KEY = 'ui:theme:primary'
const THEME_NEUTRAL_KEY = 'ui:theme:neutral'
const LOCALE_KEY = 'ui:locale'
const LOCALE_EXPLICIT_KEY = 'ui:locale:explicit'
const FONT_SIZE_KEY = 'ui:font-size'
const CURRENCY_KEY = 'ui:currency'

export type AppLocale = 'en' | 'km'

type UiColorConfig = { primary?: string; neutral?: string }

const FONT_SIZE_PX: Record<AppFontSize, string> = {
  sm: '14px',
  md: '16px',
  lg: '18px',
  xl: '20px',
}

const DEFAULT_FONT_SIZE: AppFontSize = 'md'

function normalizeFontSize(value: string | null | undefined): AppFontSize {
  if (value === 'sm' || value === 'md' || value === 'lg' || value === 'xl') return value
  return DEFAULT_FONT_SIZE
}

/**
 * Cross-page UI preferences (theme colors, font size, locale).
 * Persists to localStorage; hydrates once per session via useState guards.
 */
export const usePreferencesStore = defineStore('preferences', () => {
  const appConfig = useAppConfig()
  const i18n = useI18n()
  const appLocalization = useAppLocalization()

  const isThemeLoaded = useState('ui-theme-loaded', () => false)
  const isLocaleLoaded = useState('ui-locale-loaded', () => false)
  const isFontSizeLoaded = useState('ui-font-size-loaded', () => false)
  const fontSize = useState<AppFontSize>('ui-font-size', () => DEFAULT_FONT_SIZE)
  const isCurrencyLoaded = useState('ui-currency-loaded', () => false)
  const currency = useState<string>('ui-currency', () => 'USD')
  /** True after client-only localStorage hydration; keeps SSR and first client paint aligned. */
  const hydrated = useState('ui-preferences-hydrated', () => false)
  const availableLocales = computed<AppLocale[]>(() => {
    const configured = appLocalization.localization.value.availableLanguages
      .filter((code): code is AppLocale => code === 'en' || code === 'km')
    return configured.length ? configured : ['en', 'km']
  })

  const uiColors = computed<UiColorConfig>(() =>
    ((appConfig.ui as { colors?: UiColorConfig }).colors ?? {}),
  )

  function setThemeColors(nextColors: UiColorConfig) {
    ;(appConfig.ui as { colors?: UiColorConfig }).colors = {
      ...(appConfig.ui as { colors?: UiColorConfig }).colors,
      ...nextColors,
    }
  }

  function loadThemeFromLocal() {
    if (typeof window === 'undefined') return
    const primary = localStorage.getItem(THEME_PRIMARY_KEY) || undefined
    const neutral = localStorage.getItem(THEME_NEUTRAL_KEY) || undefined
    if (!primary && !neutral) return
    setThemeColors({
      ...(primary ? { primary } : {}),
      ...(neutral ? { neutral } : {}),
    })
  }

  function persistThemeToLocal(nextColors: UiColorConfig) {
    if (typeof window === 'undefined') return
    if (nextColors.primary) localStorage.setItem(THEME_PRIMARY_KEY, nextColors.primary)
    if (nextColors.neutral) localStorage.setItem(THEME_NEUTRAL_KEY, nextColors.neutral)
  }

  function applyThemeColor(key: 'primary' | 'neutral', color: string) {
    const next = { [key]: color } as UiColorConfig
    setThemeColors(next)
    persistThemeToLocal(next)
  }

  function applyFontSizeToDom(size: AppFontSize) {
    if (!import.meta.client) return
    const px = FONT_SIZE_PX[size]
    const root = document.documentElement
    root.style.setProperty('--app-font-size', px)
    root.style.fontSize = px
  }

  function loadFontSizeFromLocal() {
    if (typeof window === 'undefined') return
    const saved = normalizeFontSize(localStorage.getItem(FONT_SIZE_KEY))
    fontSize.value = saved
    applyFontSizeToDom(saved)
  }

  function setFontSize(size: AppFontSize) {
    const next = normalizeFontSize(size)
    fontSize.value = next
    if (import.meta.client) localStorage.setItem(FONT_SIZE_KEY, next)
    applyFontSizeToDom(next)
  }

  async function loadLocaleFromLocal() {
    if (typeof window === 'undefined') return
    await appLocalization.load()
    const savedLocale = localStorage.getItem(LOCALE_KEY)
    const isExplicit = localStorage.getItem(LOCALE_EXPLICIT_KEY) === '1'
    if (isExplicit && (savedLocale === 'en' || savedLocale === 'km') && availableLocales.value.includes(savedLocale)) {
      void i18n.setLocale(savedLocale)
      return
    }
    const configured = appLocalization.localization.value.defaultLanguage
    void i18n.setLocale(configured === 'km' ? 'km' : 'en')
  }

  function setLocale(code: AppLocale) {
    const next = availableLocales.value.includes(code)
      ? code
      : (availableLocales.value.includes(appLocalization.localization.value.defaultLanguage)
          ? appLocalization.localization.value.defaultLanguage
          : availableLocales.value[0]!)
    if (import.meta.client) {
      localStorage.setItem(LOCALE_KEY, next)
      localStorage.setItem(LOCALE_EXPLICIT_KEY, '1')
    }
    void i18n.setLocale(next)
  }

  function syncLocaleWithConfig() {
    const current = i18n.locale.value as AppLocale
    if (availableLocales.value.includes(current)) return
    const next = availableLocales.value.includes(appLocalization.localization.value.defaultLanguage)
      ? appLocalization.localization.value.defaultLanguage
      : availableLocales.value[0]!
    if (import.meta.client) localStorage.removeItem(LOCALE_EXPLICIT_KEY)
    void i18n.setLocale(next)
  }

  function loadCurrencyFromLocal() {
    if (typeof window === 'undefined') return
    const saved = localStorage.getItem(CURRENCY_KEY)
    if (saved) currency.value = saved
  }

  function setCurrency(next: string) {
    currency.value = next
    if (import.meta.client) localStorage.setItem(CURRENCY_KEY, next)
  }

  async function hydrate() {
    if (!import.meta.client || hydrated.value) return
    if (!isThemeLoaded.value) {
      loadThemeFromLocal()
      isThemeLoaded.value = true
    }
    if (!isLocaleLoaded.value) {
      await loadLocaleFromLocal()
      isLocaleLoaded.value = true
    }
    if (!isFontSizeLoaded.value) {
      loadFontSizeFromLocal()
      isFontSizeLoaded.value = true
    }
    if (!isCurrencyLoaded.value) {
      loadCurrencyFromLocal()
      isCurrencyLoaded.value = true
    }
    hydrated.value = true
  }

  return {
    uiColors,
    fontSize,
    currency,
    availableLocales,
    fontSizePx: FONT_SIZE_PX,
    hydrated: computed(() => hydrated.value),
    hydrate,
    applyThemeColor,
    setLocale,
    setCurrency,
    syncLocaleWithConfig,
    setFontSize,
  }
})
