<script setup lang="ts">
/**
 * Compact table image cell: renders the product image as a rounded
 * thumbnail, or a package placeholder when missing/broken so a
 * broken-image icon never appears.
 */
const props = withDefaults(defineProps<{
  src?: string | null
  alt?: string
  size?: 'sm' | 'md'
}>(), {
  src: null,
  alt: '',
  size: 'sm',
})

const failed = ref(false)
const resolved = computed(() => (props.src || '').trim() || null)

watch(() => props.src, () => {
  failed.value = false
})
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-sm border border-default bg-elevated align-middle"
    :class="size === 'sm' ? 'size-10' : 'size-12'"
  >
    <img
      v-if="resolved && !failed"
      :src="resolved"
      :alt="alt"
      class="h-full w-full object-cover"
      loading="lazy"
      @error="failed = true"
    >
    <UIcon
      v-else
      name="i-lucide-package"
      class="size-4 text-muted opacity-40"
    />
  </span>
</template>
