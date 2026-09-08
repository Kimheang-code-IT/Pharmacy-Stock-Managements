<script setup lang="ts">
import { en, km } from '@nuxt/ui/locale'
import { useSettingsRepositories } from '~/repositories'
import { useAppBranding } from '~/composables/settings/useAppBranding'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'
import { useAuth } from '~/composables/auth/useAuth'
import { usePreferencesStore } from '~/stores/preferences'

const colorMode = useColorMode()
const { locale, t } = useI18n()
const { applyFromAppInfo } = useAppBranding()
const preferences = usePreferencesStore()
const auth = useAuthStore()
const { appInfo } = useSettingsRepositories()
const { hydrateSessionFromApi } = useAuth()
const runtimeConfig = useRuntimeConfig()

const uiLocales: Record<string, typeof en> = { en, km }

const color = computed(() => colorMode.value === 'dark' ? '#1b1718' : 'white')
const currentLocale = computed(() => uiLocales[locale.value] || en)
const lang = computed(() => currentLocale.value.code || locale.value)
const dir = computed(() => currentLocale.value.dir || 'ltr')
const siteName = computed(() => t('core.brand.name'))
const siteTagline = computed(() => t('core.brand.tagline'))
const logoAlt = computed(() => t('core.brand.logoAlt'))
const appDescription = computed(() => t('app.description'))
const appKeywords = computed(() => t('app.keywords'))
const { absoluteUrl, absolutePageUrl } = useSeoAbsoluteUrl()
const defaultOgImage = computed(() => absoluteUrl('/og-image.png'))
const pageUrl = computed(() => absolutePageUrl())

async function hydrateStartup() {
  await preferences.hydrate()

  // Revalidate a restored bearer session from component setup. Calling
  // useAuth() inside a Nuxt plugin reaches useI18n() outside Vue setup and
  // aborts application initialization on a full page reload.
  if (runtimeConfig.public.authMode === 'bearer') {
    await hydrateSessionFromApi()
  }

  // App info is protected. Do not request it on public auth pages because an
  // expected 401 would be mistaken for an expired signed-in session.
  if (auth.isLoggedIn) {
    await Promise.all([
      appInfo.get()
        .then(info => applyFromAppInfo(info))
        .catch(() => applyFromAppInfo(null)),
      useAppLocalization().load(),
    ])
  }
}

onMounted(() => {
  // Non-blocking startup hydration — do not stall first paint.
  void hydrateStartup()
})

useHead({
  // Page title only in the tab — do not append the product name again.
  titleTemplate: (titleChunk) => {
    const chunk = titleChunk?.trim()
    if (!chunk || chunk === siteName.value) return siteName.value
    return chunk
  },
  meta: [
    { charset: 'utf-8' },
    { name: 'viewport', content: 'width=device-width, initial-scale=1' },
    { key: 'theme-color', name: 'theme-color', content: color },
    { key: 'keywords', name: 'keywords', content: appKeywords },
  ],
  link: [
    { rel: 'icon', type: 'image/png', href: '/logo.png' },
    { rel: 'apple-touch-icon', href: '/logo.png' },
  ],
  htmlAttrs: {
    lang,
    dir,
  },
})

useSeoMeta({
  description: appDescription,
  ogSiteName: siteName,
  ogTitle: () => `${siteName.value} — ${siteTagline.value}`,
  ogDescription: appDescription,
  ogImage: () => defaultOgImage.value,
  ogImageAlt: logoAlt,
  ogImageWidth: '1200',
  ogImageHeight: '630',
  ogUrl: () => pageUrl.value,
  ogType: 'website',
  twitterTitle: () => `${siteName.value} — ${siteTagline.value}`,
  twitterDescription: appDescription,
  twitterImage: () => defaultOgImage.value,
  twitterImageAlt: logoAlt,
  twitterCard: 'summary_large_image',
  robots: 'noindex, nofollow',
})
</script>

<template>
  <UApp class="h-full min-h-0" :locale="currentLocale">
    <NuxtLoadingIndicator
      color="var(--ui-primary, #e8472a)"
      error-color="#ef4444"
      :height="3"
    />
    <NuxtLayout />
    <CommonAppAccessAlertHost />
    <CommonAppConfirmHost />
  </UApp>
</template>
