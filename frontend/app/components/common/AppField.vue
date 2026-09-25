<script setup lang="ts">
import { useFormErrors } from '~/composables/useFormErrors'

/**
 * Shared form field wrapper: consistent label, required mark, help and error.
 * All App*Field controls render inside this wrapper.
 *
 * Backend validation errors (`{ detail: { field_errors } }`) are wired in here
 * automatically: every field registers the form as an inline-error sink, claims
 * its `name`, and falls back to the published message when the caller did not
 * pass an explicit `error`. That is why any page using App*Field controls shows
 * errors at the field location with no extra per-page code.
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
const { errorFor, claim } = useFormErrors()
if (props.name) claim(props.name)

// An explicit `error` (including `false`) always wins; otherwise show whatever
// the backend published for this field name.
const resolvedError = computed<string | boolean | undefined>(() => {
  if (props.error !== undefined) return props.error
  return props.name ? errorFor(props.name) : undefined
})

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
  if (!resolvedError.value) return undefined
  return typeof resolvedError.value === 'string' ? resolvedError.value : ' '
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
    <slot :error="Boolean(resolvedError)" />
  </UFormField>
</template>
