<script setup lang="ts">
/**
 * Toolbar filter select: multi-select, click a selected option again to remove it,
 * and a clear control to reset the whole filter.
 */
import {
  getFilterSearchInputConfig,
  getFilterSelectUi,
  isFilterValueActive,
} from '~/utils/filter/select-ui'
import { parseFilterQuery } from '~/utils/filter/values'

const model = defineModel<string[]>({ default: () => [] })

withDefaults(defineProps<{
  items?: Array<{ label: string, value: string }>
  placeholder?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}>(), {
  items: () => [],
  size: 'sm',
})

const { t } = useI18n()

const selected = computed({
  get: () => Array.isArray(model.value) ? model.value : parseFilterQuery(model.value),
  set: (value) => {
    model.value = parseFilterQuery(value)
  },
})

const active = computed(() => isFilterValueActive(selected.value))
const searchInput = computed(() => getFilterSearchInputConfig(t))
const ui = computed(() => getFilterSelectUi(active.value))
</script>

<template>
  <USelectMenu
    v-model="selected"
    multiple
    value-key="value"
    :items="items"
    :placeholder="placeholder"
    :aria-label="placeholder"
    :size="size"
    :search-input="searchInput"
    clear
    class="shrink-0"
    :ui="ui"
  />
</template>
