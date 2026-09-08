<script setup lang="ts">
const props = withDefaults(defineProps<{
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
}>(), {
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [number | undefined]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const value = computed({
  get: () => props.modelValue ?? undefined,
  set: (v: number | undefined) => emit('update:modelValue', v),
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
    <UInputNumber
      v-model="value"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :readonly="readonly"
      :min="min"
      :max="max"
      :step="step"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    />
  </CommonAppField>
</template>