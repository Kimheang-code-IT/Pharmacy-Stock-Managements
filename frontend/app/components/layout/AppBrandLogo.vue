<script setup lang="ts">
import logo from '~/assets/images/logo.png'

withDefaults(defineProps<{
  /** Tailwind size classes for the image. */
  imgClass?: string
}>(), {
  imgClass: 'size-full object-contain',
})

const { t } = useI18n()
</script>

<template>
  <img
    :src="logo"
    :alt="t('core.brand.logoAlt')"
    :class="imgClass"
  >
</template>
