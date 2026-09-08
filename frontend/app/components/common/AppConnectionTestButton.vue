<script setup lang="ts">
const props = withDefaults(defineProps<{
  label?: string
  labelKey?: string
  loading?: boolean
  disabled?: boolean
  color?: 'primary' | 'neutral' | 'success'
  icon?: string
}>(), {
  labelKey: 'core.connection.test',
  loading: false,
  disabled: false,
  color: 'neutral',
  icon: 'i-lucide-plug-zap',
})

const emit = defineEmits<{
  click: []
}>()

const { t, te } = useI18n()

const labelText = computed(() => {
  if (props.label) return props.label
  if (props.labelKey && te(props.labelKey)) return t(props.labelKey)
  return t('core.connection.test')
})
</script>

<template>
  <UButton
    :icon="icon"
    :color="color"
    variant="soft"
    :loading="loading"
    :disabled="disabled || loading"
    @click="emit('click')"
  >
    {{ labelText }}
  </UButton>
</template>
