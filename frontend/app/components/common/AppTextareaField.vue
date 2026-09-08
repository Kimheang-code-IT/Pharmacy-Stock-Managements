<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: string
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
  rows?: number
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  modelValue: '',
  rows: 3,
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const value = computed({
  get: () => props.modelValue ?? '',
  set: (v: string) => emit('update:modelValue', v),
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
    <UTextarea
      v-model="value"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :readonly="readonly"
      :rows="rows"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    />
  </CommonAppField>
</template>