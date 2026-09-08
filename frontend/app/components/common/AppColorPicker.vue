<script setup lang="ts">
const model = defineModel<string>({ default: '#2563eb' })

const props = withDefaults(defineProps<{
  label?: string
  labelKey?: string
  help?: string
  disabled?: boolean
}>(), {
  disabled: false,
})

const { t, te } = useI18n()

const labelText = computed(() => {
  if (props.label) return props.label
  if (props.labelKey && te(props.labelKey)) return t(props.labelKey)
  return t('core.common.color')
})

const PRESETS = [
  '#2563eb',
  '#16a34a',
  '#ca8a04',
  '#ea580c',
  '#dc2626',
  '#7c3aed',
  '#db2777',
  '#0891b2',
  '#64748b',
  '#0f172a',
]
</script>

<template>
  <UFormField :label="labelText" :help="props.help || undefined">
    <div class="flex flex-wrap items-center gap-2">
      <input
        v-model="model"
        type="color"
        class="size-11 cursor-pointer rounded-sm border border-default bg-transparent p-0.5"
        :disabled="props.disabled"
        :aria-label="labelText"
      >
      <UInput
        v-model="model"
        class="w-32"
        size="md"
        :disabled="props.disabled"
        placeholder="#2563eb"
      />
      <UButton
        v-for="swatch in PRESETS"
        :key="swatch"
        type="button"
        color="neutral"
        variant="ghost"
        size="xs"
        class="size-6 rounded-full p-0 ring-1 ring-default transition hover:scale-110"
        :class="model === swatch ? 'ring-2 ring-primary' : ''"
        :style="{ backgroundColor: swatch }"
        :disabled="props.disabled"
        :aria-label="swatch"
        @click="model = swatch"
      />
    </div>
  </UFormField>
</template>
