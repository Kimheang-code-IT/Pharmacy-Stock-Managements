<script setup lang="ts">
/**
 * Shared readable width for document forms / comments / alerts.
 * Keeps fields from stretching edge-to-edge; side gutters grow with viewport.
 */
withDefaults(defineProps<{
  /** Use for permission matrices, builders, and other dense editors. */
  wide?: boolean
}>(), {
  wide: false,
})
</script>

<template>
  <div
    class="mx-auto w-full"
    :class="wide
      ? 'max-w-5xl px-4 sm:px-6 md:px-8 lg:max-w-6xl lg:px-10 xl:max-w-7xl xl:px-12'
      : 'max-w-2xl px-4 sm:max-w-3xl sm:px-6 md:px-8 lg:max-w-4xl lg:px-10 xl:max-w-5xl xl:px-12'"
  >
    <slot />
  </div>
</template>
