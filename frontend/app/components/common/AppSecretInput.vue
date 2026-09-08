<script setup lang="ts">
/**
 * Deprecated alias — use CommonAppSecretField directly.
 * Kept so existing settings forms keep working unchanged.
 */
withDefaults(defineProps<{
  modelValue?: string
  label?: string
  labelKey?: string
  name?: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  autocomplete?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  modelValue: '',
  autocomplete: 'new-password',
  size: 'md',
})

defineEmits<{
  'update:modelValue': [string]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()
</script>

<template>
  <CommonAppSecretField
    :model-value="modelValue"
    :label="label"
    :label-key="labelKey"
    :name="name"
    :placeholder="placeholder"
    :required="required"
    :disabled="disabled"
    :help="help"
    :help-key="helpKey"
    :error="error"
    :autocomplete="autocomplete"
    :size="size"
    :class="$props.class"
    @update:model-value="$emit('update:modelValue', $event)"
    @blur="$emit('blur', $event)"
    @focus="$emit('focus', $event)"
  />
</template>