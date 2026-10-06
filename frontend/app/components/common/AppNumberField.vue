<script setup lang="ts">
import { currencySymbol, numberInputFormat } from '~/utils/format/format-service'

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
  /** Money field: renders the currency symbol at the end of the input. */
  money?: boolean
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

const moneySymbol = computed(() => (props.money ? currencySymbol(props.currency) : ''))

/** Money fields follow the System Settings number format; plain numbers don't. */
const moneyFormatOptions = computed<Intl.NumberFormatOptions | undefined>(() =>
  props.money || props.currency ? numberInputFormat().options : undefined)
const moneyLocale = computed(() => (moneyFormatOptions.value ? numberInputFormat().locale : undefined))
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
        :increment="false"
        :decrement="false"
        :step-snapping="false"
        :format-options="moneyFormatOptions"
        :locale="moneyLocale"
        :ui="{ base: 'pe-7' }"
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
    <div
      v-else-if="money"
      class="relative w-full"
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
        :increment="false"
        :decrement="false"
        :step-snapping="false"
        :format-options="moneyFormatOptions"
        :locale="moneyLocale"
        :class="[$props.class, fieldControlClass(Boolean(error))]"
        @blur="emit('blur', $event)"
        @focus="emit('focus', $event)"
      />
      <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center text-sm text-muted">{{ moneySymbol }}</span>
    </div>
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