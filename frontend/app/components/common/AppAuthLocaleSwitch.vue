<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import { usePreferencesStore, type AppLocale } from '~/stores/preferences'

const preferences = usePreferencesStore()
const { locale, locales } = useI18n()

const currentLabel = computed(() => {
  const match = (locales.value || []).find((loc: { code?: string }) => loc.code === locale.value)
  return match?.name || String(locale.value).toUpperCase()
})

const items = computed<DropdownMenuItem[][]>(() => [
  (locales.value || [])
    .filter((loc: { code?: string }) => preferences.availableLocales.includes(loc.code as AppLocale))
    .map((loc: { name?: string; code?: string }) => ({
    label: loc.name || loc.code,
    type: 'checkbox' as const,
    checked: locale.value === loc.code,
    onSelect: (e: Event) => {
      e.preventDefault()
      if (loc.code === 'en' || loc.code === 'km') {
        preferences.setLocale(loc.code as AppLocale)
      }
    },
    })),
])
</script>

<template>
  <UDropdownMenu :items="items" :content="{ align: 'end', sideOffset: 8 }">
    <UButton
      color="neutral"
      variant="ghost"
      size="sm"
      icon="i-lucide-languages"
      :label="currentLabel"
      trailing-icon="i-lucide-chevron-down"
      class="bg-default/80 shadow-sm ring-1 ring-default backdrop-blur-sm"
      :aria-label="$t('settings.language')"
    />
  </UDropdownMenu>
</template>
