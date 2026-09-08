<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

withDefaults(defineProps<{
  items: DropdownMenuItem[][]
  loading?: boolean
}>(), {
  loading: false,
})

const { t } = useI18n()
</script>

<template>
  <div class="flex items-center justify-end">
    <UDropdownMenu :items="items" :content="{ align: 'end' }" :aria-label="t('app.ui.actions')">
      <UButton
        icon="i-lucide-ellipsis"
        color="neutral"
        variant="ghost"
        size="xs"
        :loading="loading"
        :aria-label="t('app.ui.actions')"
      />
    </UDropdownMenu>
  </div>
</template>
