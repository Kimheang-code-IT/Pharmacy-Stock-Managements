<script setup lang="ts">
/**
 * Shared form field wrapper: consistent label, required mark, help and error.
 * All App*Field controls render inside this wrapper.
 */
const props = withDefaults(defineProps<{
  label?: string
  labelKey?: string
  name?: string
  required?: boolean
  help?: string
  helpKey?: string
  /** Error message; also drives error styling on the control. */
  error?: string | boolean
  description?: string
  hint?: string
  /** Hide the required asterisk even when required. */
  hideRequiredMark?: boolean
}>(), {
  hideRequiredMark: false,
})

const { t, te } = useI18n()

const labelText = computed(() => {
  if (props.label) return props.label
  if (props.labelKey && te(props.labelKey)) return t(props.labelKey)
  return undefined
})

const helpText = computed(() => {
  if (props.help) return props.help
  if (props.helpKey && te(props.helpKey)) return t(props.helpKey)
  return undefined
})

const errorText = computed(() => {
  if (!props.error) return undefined
  return typeof props.error === 'string' ? props.error : ' '
})
</script>

<template>
  <UFormField
    :label="labelText"
    :name="name"
    :required="required"
    :help="helpText"
    :error="errorText"
    :hint="hint"
    :description="description"
    :ui="{ label: required && hideRequiredMark ? '[&_.text-error]:hidden' : undefined }"
  >
    <slot :error="Boolean(error)" />
  </UFormField>
</template>