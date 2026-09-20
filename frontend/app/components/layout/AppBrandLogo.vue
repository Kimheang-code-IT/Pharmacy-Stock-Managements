<script setup lang="ts">
withDefaults(defineProps<{
  /** Tailwind size classes for the image. */
  imgClass?: string
}>(), {
  imgClass: 'size-full object-contain',
})

const { t } = useI18n()

// Live system logo — served from frontend/public/logo.png. Replacing that one
// file updates the sidebar, auth pages and the About dialog; the favicon and
// apple-touch-icon already point at the same URL (see nuxt.config.ts / app.vue).
const logo = '/logo.png'
</script>

<template>
  <img
    :src="logo"
    :alt="t('core.brand.logoAlt')"
    :class="imgClass"
  >
</template>
