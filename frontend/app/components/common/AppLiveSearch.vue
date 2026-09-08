<script setup lang="ts">
/**
 * Reusable live search input — grey active border, search icon, clear (X) when non-empty.
 */
import { getFilterSearchUi, isFilterValueActive } from '~/utils/filter/select-ui'

defineOptions({ inheritAttrs: false })

const modelValue = defineModel<string>({ default: '' })

withDefaults(
  defineProps<{
    placeholder?: string
    size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
    disabled?: boolean
    clearable?: boolean
  }>(),
  {
    size: 'sm',
    clearable: true,
  },
)

const attrs = useAttrs()
const { t } = useI18n()

const hasValue = computed(() => isFilterValueActive(modelValue.value))
const ui = computed(() => ({
  ...getFilterSearchUi(hasValue.value),
  trailing: 'pe-1',
}))

function clearSearch(event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  modelValue.value = ''
}
</script>

<template>
  <UInput
    v-bind="attrs"
    v-model="modelValue"
    class="app-live-search"
    type="text"
    inputmode="search"
    enterkeyhint="search"
    autocomplete="off"
    autocorrect="off"
    spellcheck="false"
    icon="i-lucide-search"
    :placeholder="placeholder"
    :size="size"
    :disabled="disabled"
    color="neutral"
    :ui="ui"
  >
    <template v-if="clearable && hasValue && !disabled" #trailing>
      <UButton
        color="neutral"
        variant="link"
        :size="size"
        icon="i-lucide-circle-x"
        class="px-0"
        :aria-label="t('core.common.clear')"
        :title="t('core.common.clear')"
        @mousedown.prevent
        @click="clearSearch"
      />
    </template>
  </UInput>
</template>
