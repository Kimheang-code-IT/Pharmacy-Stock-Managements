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
  /** When set, renders a USD/KHR toggle at the end of the input. */
  currency?: 'USD' | 'KHR'
}>(), {
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [number | undefined]
  'update:currency': ['USD' | 'KHR']
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const { t } = useI18n()

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

function onCurrencySelect(value: 'USD' | 'KHR') {
  if (value !== props.currency) emit('update:currency', value)
}

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
    <UFieldGroup
      v-if="currency"
      :size="size"
      class="w-full"
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
      <UButton
        v-for="option in currencyOptions"
        :key="option.value"
        :label="option.symbol"
        :color="currency === option.value ? 'primary' : 'neutral'"
        :variant="currency === option.value ? 'soft' : 'outline'"
        :disabled="disabled"
        :title="t(option.labelKey)"
        :aria-label="t(option.labelKey)"
        :aria-pressed="currency === option.value"
        @click="onCurrencySelect(option.value)"
      />
    </UFieldGroup>
    <UInputNumber
      v-else
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