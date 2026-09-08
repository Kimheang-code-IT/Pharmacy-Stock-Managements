<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: boolean | string
  label?: string
  labelKey?: string
  name?: string
  required?: boolean
  disabled?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}>(), {
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [boolean]
}>()

const { t, te } = useI18n()

const labelText = computed(() => {
  if (props.label) return props.label
  if (props.labelKey && te(props.labelKey)) return t(props.labelKey)
  return undefined
})

const value = computed({
  get: () => props.modelValue === true || props.modelValue === 'Yes',
  set: (v: boolean) => emit('update:modelValue', v),
})
</script>

<template>
  <CommonAppField :help="help" :help-key="helpKey" :error="error">
    <UCheckbox
      v-model="value"
      :label="labelText"
      :name="name"
      :required="required"
      :disabled="disabled"
      :size="size"
    />
  </CommonAppField>
</template>