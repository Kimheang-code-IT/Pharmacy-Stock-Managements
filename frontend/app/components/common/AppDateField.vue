<script setup lang="ts">
type DatePickerGranularity = 'day' | 'hour' | 'minute' | 'second'

const props = withDefaults(defineProps<{
  modelValue?: string | null
  label?: string
  labelKey?: string
  name?: string
  required?: boolean
  disabled?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  granularity?: DatePickerGranularity
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  granularity: 'day',
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
}>()
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
    <CommonAppInputDate
      :model-value="modelValue"
      :granularity="granularity"
      :required="required"
      :disabled="disabled"
      :size="size"
      :class="[props.class, fieldControlClass(Boolean(error))].filter(Boolean).join(' ')"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </CommonAppField>
</template>