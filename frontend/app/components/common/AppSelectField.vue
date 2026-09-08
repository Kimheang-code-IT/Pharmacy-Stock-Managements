<script setup lang="ts">
export type AppFieldSelectItem = string | { label: string, value: string }

const props = withDefaults(defineProps<{
  modelValue?: string | number | null
  items?: readonly AppFieldSelectItem[]
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
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  items: () => [],
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
    <USelect
      v-model="value"
      :items="[...items]"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :readonly="readonly"
      value-key="value"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    />
  </CommonAppField>
</template>