<script setup lang="ts">
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const config = useRuntimeConfig()

const appVersion = String(config.public.appVersion || '0.1.0')
const versionLabel = computed(() =>
  appVersion.startsWith('v') ? appVersion : `v${appVersion}`,
)

const socials = [
  { icon: 'i-simple-icons-github', label: 'GitHub', href: 'https://github.com' },
  { icon: 'i-lucide-message-circle', label: 'Support', href: '#' },
]
</script>

<template>
  <UModal
    v-model:open="open"
    scrollable
    :title="t('settings.about')"
    :dismissible="false"
    :close="{ color: 'primary', variant: 'outline', class: 'rounded-full' }"
    :ui="{
      overlay: 'place-items-start justify-items-center pt-[5vh] sm:pt-[5vh]',
      content: 'w-[calc(100%-2rem)] max-w-md sm:max-w-md',
    }"
  >
    <template #body>
      <div class="flex flex-col items-center gap-5 pb-1 text-center">
        <div class="flex flex-col items-center gap-2">
          <div class="relative inline-flex">
            <LayoutAppBrandLogo img-class="size-16 object-contain" />
            <span
              class="absolute -end-2 -top-2 rounded-full bg-elevated px-1.5 py-0.5 text-[10px] font-semibold leading-none text-toned ring-1 ring-default shadow-sm"
            >
              {{ versionLabel }}
            </span>
          </div>

          <h2 class="text-2xl font-semibold tracking-tight text-highlighted">
            {{ t('core.brand.name') }}
          </h2>
          <p class="max-w-xs text-sm text-muted">
            {{ t('core.brand.tagline') }}
          </p>
        </div>

        <div class="flex items-center gap-3">
          <UButton
            v-for="social in socials"
            :key="social.label"
            :icon="social.icon"
            :to="social.href"
            target="_blank"
            color="neutral"
            variant="ghost"
            size="sm"
            square
            :aria-label="social.label"
          />
        </div>
      </div>
    </template>

    <template #footer>
      <p class="w-full text-center text-xs text-muted">
        {{ t('settings.aboutCopyright') }}
      </p>
    </template>
  </UModal>
</template>
