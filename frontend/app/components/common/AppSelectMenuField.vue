<script setup lang="ts">
export type AppFieldComboboxItem = string | { label: string, value: string }

const props = withDefaults(defineProps<{
  modelValue?: string | number | null
  items?: readonly AppFieldComboboxItem[]
  label?: string
  labelKey?: string
  name?: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  /** Show the inline search box in the dropdown. */
  searchInput?: boolean
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  items: () => [],
  searchInput: false,
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const value = computed({
  get: () => (props.modelValue == null ? undefined : String(props.modelValue)),
  set: (v: string | undefined) => emit('update:modelValue', v ?? ''),
})
</script>

<template>
  <CommonAppField
    :label="label"
    :label-key="labelKey"
    :name="name"
    :required="required"
    :help="help"
    :help-key="helpKey"
    :error="error"
  >
    <USelectMenu
      v-model="value"
      :items="[...items]"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      value-key="value"
      :search-input="searchInput"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    />
  </CommonAppField>
</template>