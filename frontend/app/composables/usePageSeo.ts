type PageSeoOptions = {
  /** Browser tab / document title — page name only (no brand suffix). */
  title: MaybeRefOrGetter<string>
  description?: MaybeRefOrGetter<string | undefined | null>
  /** Default: noindex for authenticated app; auth pages should pass `index, follow`. */
  robots?: MaybeRefOrGetter<string | undefined>
  /** Relative path (`/og-image.png`) or absolute URL. Resolved to absolute for crawlers. */
  ogImage?: MaybeRefOrGetter<string | undefined>
}

/** Default social preview image. */
const DEFAULT_OG_IMAGE = '/og-image.png'

/**
 * Per-page SEO. Titles are the page label only — brand is not appended
 * (see `titleTemplate` in `app.vue`).
 *
 * Social previews (Telegram, WhatsApp, Facebook, X) require absolute
 * `og:image` / `twitter:image` URLs — relative paths will not show an image.
 */
export function usePageSeo(options: PageSeoOptions) {
  const { t } = useI18n()
  const { absoluteUrl, absolutePageUrl } = useSeoAbsoluteUrl()

  const title = computed(() => {
    const value = toValue(options.title)?.trim()
    return value || t('core.brand.name')
  })

  const description = computed(() => {
    const value = toValue(options.description)?.trim()
    return value || t('app.description')
  })

  const robots = computed(() => toValue(options.robots) || 'noindex, nofollow')
  const ogImage = computed(() =>
    absoluteUrl(toValue(options.ogImage) || DEFAULT_OG_IMAGE),
  )
  const pageUrl = computed(() => absolutePageUrl())

  useHead(() => ({
    title: title.value,
  }))

  useSeoMeta({
    title: () => title.value,
    description: () => description.value,
    ogTitle: () => title.value,
    ogDescription: () => description.value,
    ogImage: () => ogImage.value,
    ogImageAlt: () => t('core.brand.logoAlt'),
    ogImageWidth: '1200',
    ogImageHeight: '630',
    ogUrl: () => pageUrl.value || undefined,
    ogType: 'website',
    twitterTitle: () => title.value,
    twitterDescription: () => description.value,
    twitterImage: () => ogImage.value,
    twitterImageAlt: () => t('core.brand.logoAlt'),
    // Large card so messengers show a big preview image (like YouTube links).
    twitterCard: 'summary_large_image',
    robots: () => robots.value,
  })
}
