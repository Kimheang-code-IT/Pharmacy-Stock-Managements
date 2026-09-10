<script setup lang="ts">
/**
 * Money/decimal input: decimal-safe step and non-negative default bounds.
 */
withDefaults(defineProps<{
  modelValue?: number | null | undefined
  label?: string
  labelKey?: string
  name?: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  readonly?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  min?: number
  max?: number
  step?: number
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
  /** When set, renders a USD/KHR toggle at the end of the input. */
  currency?: 'USD' | 'KHR'
}>(), {
  min: 0,
  step: 0.01,
  size: 'md',
})

defineEmits<{
  'update:modelValue': [number | undefined]
  'update:currency': ['USD' | 'KHR']
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()
</script>

<template>
  <CommonAppNumberField
    :model-value="modelValue"
    :label="label"
    :label-key="labelKey"
    :name="name"
    :placeholder="placeholder"
    :required="required"
    :disabled="disabled"
    :readonly="readonly"
    :help="help"
    :help-key="helpKey"
    :error="error"
    :min="min"
    :max="max"
    :step="step"
    :size="size"
    :class="$props.class"
    :currency="currency"
    @update:model-value="$emit('update:modelValue', $event)"
    @update:currency="$emit('update:currency', $event)"
    @blur="$emit('blur', $event)"
    @focus="$emit('focus', $event)"
  />
</template>