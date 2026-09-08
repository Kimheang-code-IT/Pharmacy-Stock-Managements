<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: string | number
  label?: string
  labelKey?: string
  name?: string
  type?: 'text' | 'email' | 'password' | 'url' | 'tel' | 'search'
  placeholder?: string
  required?: boolean
  disabled?: boolean
  readonly?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  icon?: string
  autocomplete?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  modelValue: '',
  type: 'text',
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const value = computed({
  get: () => (props.modelValue == null ? '' : String(props.modelValue)),
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
    <UInput
      v-model="value"
      :type="type"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :readonly="readonly"
      :icon="icon"
      :autocomplete="autocomplete"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    />
  </CommonAppField>
</template>