<script setup lang="ts">
import type { FieldOption } from '~/types/stock-pos/common'

const model = defineModel<string[]>({ default: () => [] })

const props = withDefaults(defineProps<{
  items?: FieldOption[]
  placeholder?: string
  disabled?: boolean
  loading?: boolean
  allowCustom?: boolean
}>(), {
  items: () => [],
  allowCustom: false,
})

const emit = defineEmits<{
  search: [value: string]
}>()

const root = ref<HTMLElement | null>(null)
const query = ref('')
const open = ref(false)
const activeIndex = ref(0)

const normalizedQuery = computed(() => query.value.trim().replace(/^@+/, '').trim())
const selected = computed(() => new Set(model.value.map(value => value.toLocaleLowerCase())))
const suggestions = computed(() => {
  const needle = normalizedQuery.value.toLocaleLowerCase()
  return props.items
    .filter(item => !selected.value.has(String(item.value).toLocaleLowerCase()))
    .filter(item => !needle || `${item.label} ${item.value}`.toLocaleLowerCase().includes(needle))
    .slice(0, 10)
})

watch(normalizedQuery, (value) => {
  activeIndex.value = 0
  emit('search', value)
})

onClickOutside(root, () => { open.value = false })

function labelFor(value: string) {
  return props.items.find(item => String(item.value) === value)?.label || value
}

function add(value: string) {
  const next = value.trim()
  if (!next || props.disabled || selected.value.has(next.toLocaleLowerCase())) return
  model.value = [...model.value, next]
  query.value = ''
  open.value = true
}

function remove(value: string) {
  if (props.disabled) return
  model.value = model.value.filter(item => item !== value)
}

function onEnter() {
  const option = suggestions.value[activeIndex.value]
  if (option) {
    add(String(option.value))
    return
  }
  if (props.allowCustom) add(normalizedQuery.value)
}

function onBackspace() {
  if (query.value || !model.value.length) return
  remove(model.value[model.value.length - 1] || '')
}

function moveActive(offset: number) {
  if (!suggestions.value.length) return
  open.value = true
  activeIndex.value = (activeIndex.value + offset + suggestions.value.length) % suggestions.value.length
}
</script>

<template>
  <div ref="root" class="relative">
    <div
      class="flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-sm border border-default bg-default px-3 py-2 shadow-xs transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20"
      :class="disabled ? 'cursor-not-allowed opacity-60' : ''"
      @click="!disabled && (open = true)"
    >
      <span
        v-for="value in model"
        :key="value"
        class="inline-flex max-w-full items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary ring-1 ring-primary/20"
      >
        <UIcon name="i-lucide-at-sign" class="size-3 shrink-0" />
        <span class="max-w-48 truncate">{{ labelFor(value) }}</span>
        <button
          v-if="!disabled"
          type="button"
          class="grid size-3.5 shrink-0 place-items-center rounded-full hover:bg-primary/15"
          :aria-label="$t('actions.remove')"
          @click.stop="remove(value)"
        >
          <UIcon name="i-lucide-x" class="size-2.5" />
        </button>
      </span>

      <input
        v-model="query"
        type="text"
        class="min-w-28 flex-1 border-0 bg-transparent px-0.5 py-0.5 text-base text-highlighted outline-none placeholder:text-dimmed disabled:cursor-not-allowed"
        :placeholder="model.length ? $t('core.fields.mentionSearchMore') : placeholder"
        :disabled="disabled"
        autocomplete="off"
        @focus="open = true"
        @keydown.down.prevent="moveActive(1)"
        @keydown.up.prevent="moveActive(-1)"
        @keydown.enter.prevent="onEnter"
        @keydown.backspace="onBackspace"
        @keydown.esc="open = false"
      >

      <UIcon v-if="loading" name="i-lucide-loader-circle" class="size-4 animate-spin text-muted" />
      <UIcon v-else name="i-lucide-users" class="size-4 text-muted" />
    </div>

    <div
      v-if="open && !disabled && (suggestions.length || (allowCustom && normalizedQuery))"
      class="absolute inset-x-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-sm border border-default bg-default p-1 shadow-lg"
    >
      <button
        v-for="(option, index) in suggestions"
        :key="String(option.value)"
        type="button"
        class="flex w-full items-center gap-2 rounded-sm px-2.5 py-2 text-left text-sm text-highlighted"
        :class="index === activeIndex ? 'bg-elevated' : 'hover:bg-elevated/70'"
        @mouseenter="activeIndex = index"
        @mousedown.prevent="add(String(option.value))"
      >
        <span class="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {{ String(option.label || option.value).trim().charAt(0).toUpperCase() }}
        </span>
        <span class="min-w-0 flex-1 truncate">{{ option.label }}</span>
      </button>

      <button
        v-if="allowCustom && normalizedQuery && !suggestions.some(item => String(item.value).toLocaleLowerCase() === normalizedQuery.toLocaleLowerCase())"
        type="button"
        class="flex w-full items-center gap-2 rounded-sm px-2.5 py-2 text-left text-sm text-primary hover:bg-primary/5"
        @mousedown.prevent="add(normalizedQuery)"
      >
        <UIcon name="i-lucide-plus" class="size-4" />
        {{ $t('core.fields.mentionAdd', { name: normalizedQuery }) }}
      </button>
    </div>
  </div>
</template>
