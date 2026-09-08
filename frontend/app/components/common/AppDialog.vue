<script setup lang="ts">
/**
 * Single reusable dialog shell for the whole app.
 * Confirm dialogs, access/session alerts and feature modals all render
 * through this component — do not introduce a second UModal-based shell.
 *
 * Width rules: default dialogs stay at the Nuxt UI theme width (max-w-lg).
 * `wide` renders a viewport-scaled dialog — ~70vw on desktop (spec rule for
 * the stock quantity-history dialogs) and ~95vw on mobile/tablet.
 */
const props = withDefaults(defineProps<{
  title?: string
  titleKey?: string
  description?: string
  descriptionKey?: string
  icon?: string
  /** Icon tone (drives badge color). */
  color?: 'primary' | 'neutral' | 'success' | 'warning' | 'error' | 'info'
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  /** Wide viewport-scaled dialog: ~70vw on desktop, ~95vw on small screens. */
  wide?: boolean
  /** Allow closing via overlay / Esc / close button. */
  dismissible?: boolean
  loading?: boolean
  /** Block closing while `loading` is true. */
  preventCloseOnLoading?: boolean
  /** Extra UModal ui overrides (e.g. overlay z-index). */
  ui?: Record<string, unknown>
}>(), {
  color: 'primary',
  size: 'md',
  wide: false,
  dismissible: true,
  loading: false,
  preventCloseOnLoading: true,
})

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  close: []
}>()

const { t, te } = useI18n()

const resolvedTitle = computed(() => {
  if (props.title) return props.title
  if (props.titleKey && te(props.titleKey)) return t(props.titleKey)
  return ''
})

const resolvedDescription = computed(() => {
  if (props.description) return props.description
  if (props.descriptionKey && te(props.descriptionKey)) return t(props.descriptionKey)
  return ''
})

const canClose = computed(() => props.dismissible && !(props.loading && props.preventCloseOnLoading))

const WIDE_CONTENT_CLASS = 'w-[95vw] max-w-[95vw] sm:w-[70vw] sm:max-w-[70vw]'

const mergedUi = computed<Record<string, unknown>>(() => {
  if (!props.wide) return props.ui ?? {}
  const extra = props.ui?.content
  return {
    ...props.ui,
    content: typeof extra === 'string' && extra
      ? `${WIDE_CONTENT_CLASS} ${extra}`
      : WIDE_CONTENT_CLASS,
  }
})

const iconTone = computed(() => {
  const tones: Record<string, string> = {
    primary: 'bg-primary/10 text-primary',
    neutral: 'bg-elevated text-muted',
    success: 'bg-success/10 text-success',
    warning: 'bg-warning/10 text-warning',
    error: 'bg-error/10 text-error',
    info: 'bg-info/10 text-info',
  }
  return tones[props.color] || tones.primary
})

function requestClose(value: boolean) {
  if (!value && !canClose.value) return
  if (!value) emit('close')
  open.value = value
}
</script>

<template>
  <UModal
    :open="open"
    :dismissible="canClose"
    :close="canClose"
    :size="size"
    :ui="mergedUi"
    @update:open="requestClose"
  >
    <template #title>
      <div class="flex items-center gap-2.5">
        <span
          v-if="icon"
          class="flex size-8 shrink-0 items-center justify-center rounded-full"
          :class="iconTone"
        >
          <UIcon :name="icon" class="size-4" />
        </span>
        <span class="min-w-0 text-base font-semibold text-highlighted">{{ resolvedTitle }}</span>
      </div>
    </template>

    <template v-if="resolvedDescription" #description>
      <p class="text-sm text-muted">{{ resolvedDescription }}</p>
    </template>

    <template #body>
      <slot />
    </template>

    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>

    <template v-if="$slots.header" #header>
      <slot name="header" />
    </template>
  </UModal>
</template>