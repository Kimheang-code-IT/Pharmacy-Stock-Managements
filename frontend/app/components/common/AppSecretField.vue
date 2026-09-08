<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: string
  label?: string
  labelKey?: string
  name?: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  help?: string
  helpKey?: string
  error?: string | boolean
  autocomplete?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  modelValue: '',
  autocomplete: 'new-password',
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
  blur: [FocusEvent]
  focus: [FocusEvent]
}>()

const { t } = useI18n()
const revealed = ref(false)

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
    <UInput
      v-model="value"
      :type="revealed ? 'text' : 'password'"
      :name="name"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :autocomplete="autocomplete"
      :size="size"
      :class="[$props.class, fieldControlClass(Boolean(error))]"
      :ui="{ trailing: 'pe-1' }"
      @blur="emit('blur', $event)"
      @focus="emit('focus', $event)"
    >
      <template #trailing>
        <UButton
          :icon="revealed ? 'i-lucide-eye-off' : 'i-lucide-eye'"
          color="neutral"
          variant="link"
          size="sm"
          :aria-label="revealed ? t('core.common.hideSecret') : t('core.common.showSecret')"
          :disabled="disabled"
          @click="revealed = !revealed"
        />
      </template>
    </UInput>
  </CommonAppField>
</template>