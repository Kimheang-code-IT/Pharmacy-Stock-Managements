<script setup lang="ts">
import type { DateValue } from '@internationalized/date'
import type { DatePickerGranularity } from '~/utils/date-picker'
import {
  isDateTimeGranularity,
  parsePickerValue,
  serializePickerValue,
  datePickerPopoverContent,
} from '~/utils/date-picker'
import { getFilterDateUi, isFilterValueActive } from '~/utils/filter/select-ui'
import { usePreferencesStore } from '~/stores/preferences'

const start = defineModel<string>('start', { default: '' })
const end = defineModel<string>('end', { default: '' })

const props = withDefaults(defineProps<{
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  disabled?: boolean
  granularity?: DatePickerGranularity
  label?: string
  placeholder?: string
  class?: string
  /** Full-width layout for dialogs/forms. */
  inline?: boolean
}>(), {
  size: 'sm',
  granularity: 'minute',
})

const { t } = useI18n()
const preferences = usePreferencesStore()

const inputDate = useTemplateRef<{ inputsRef?: Array<{ $el?: HTMLElement }> } | null>('inputDate')
const pickerAnchor = useTemplateRef<HTMLElement | null>('pickerAnchor')

const isDateTime = computed(() => isDateTimeGranularity(props.granularity))

const hasActiveFilter = computed(() =>
  isFilterValueActive(start.value) || isFilterValueActive(end.value),
)

const pickerTitle = computed(() => props.label || t('core.fields.meetingDate'))

const dateUi = computed(() => getFilterDateUi(hasActiveFilter.value, {
  isDateTime: isDateTime.value,
  isRange: true,
  fitContent: !props.inline,
  fullWidth: props.inline,
  fontSize: preferences.fontSize,
}))

const pickerIcon = computed(() =>
  isDateTime.value ? 'i-lucide-calendar-clock' : 'i-lucide-calendar',
)

/** Shared with UInputDate + UCalendar in popover (Nuxt UI pattern). */
const dateRangeValue = computed({
  get() {
    const startValue = parsePickerValue(start.value, isDateTime.value)
    const endValue = parsePickerValue(end.value, isDateTime.value)
    if (!startValue && !endValue) return undefined
    return {
      start: startValue ?? endValue!,
      end: endValue ?? startValue!,
    }
  },
  set(value: { start?: DateValue, end?: DateValue } | null | undefined) {
    if (!value?.start && !value?.end) {
      start.value = ''
      end.value = ''
      return
    }
    start.value = value.start ? serializePickerValue(value.start) : ''
    end.value = value.end ? serializePickerValue(value.end) : ''
  },
})

function clearFilter() {
  start.value = ''
  end.value = ''
}
</script>

<template>
  <div
    class="items-center gap-1.5"
    :class="[
      props.class,
      inline ? 'flex w-full min-w-0' : 'inline-flex w-auto max-w-full',
    ]"
  >
    <div
      ref="pickerAnchor"
      class="min-w-0"
      :class="inline ? 'w-full' : 'w-auto max-w-full'"
    >
      <UInputDate
        ref="inputDate"
        v-model="dateRangeValue"
        range
        fixed
        trailing
        :granularity="granularity"
        :disabled="disabled"
        :size="size"
        color="neutral"
        variant="outline"
        :class="inline ? 'w-full min-w-0' : 'w-auto max-w-full'"
        :ui="dateUi"
        :aria-label="pickerTitle"
      >
        <template #trailing>
          <UPopover
            :reference="pickerAnchor ?? inputDate?.inputsRef?.[0]?.$el"
            :content="datePickerPopoverContent"
          >
            <UButton
              color="neutral"
              variant="link"
              :size="size === 'xs' || size === 'sm' ? 'sm' : size"
              :icon="pickerIcon"
              class="shrink-0 px-2 text-muted"
              :aria-label="pickerTitle"
              :disabled="disabled"
            />

            <template #content>
              <CommonAppDatePickerPopover
                v-model:range-value="dateRangeValue"
                mode="range"
                :granularity="granularity"
                :disabled="disabled"
              />
            </template>
          </UPopover>
        </template>
      </UInputDate>
    </div>

    <UButton
      v-if="hasActiveFilter"
      icon="i-lucide-x"
      color="neutral"
      variant="ghost"
      size="xs"
      square
      class="shrink-0"
      :aria-label="t('core.common.clear')"
      :title="t('core.common.clear')"
      :disabled="disabled"
      @click="clearFilter"
    />
  </div>
</template>
