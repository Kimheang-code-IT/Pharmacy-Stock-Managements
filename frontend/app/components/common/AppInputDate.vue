<script setup lang="ts">
import { today, getLocalTimeZone } from '@internationalized/date'
import type { DateValue } from '@internationalized/date'
import type { DatePickerGranularity } from '~/utils/date-picker'
import {
  isDateTimeGranularity,
  parsePickerValue,
  serializePickerValue,
  datePickerPopoverContent,
} from '~/utils/date-picker'
import { formatDateParts } from '~/utils/format/format-service'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

const props = withDefaults(defineProps<{
  modelValue?: string | null
  disabled?: boolean
  required?: boolean
  granularity?: DatePickerGranularity
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  class?: string
}>(), {
  granularity: 'day',
  size: 'md',
})

const emit = defineEmits<{
  'update:modelValue': [string]
}>()

const { localization, formatTime } = useAppLocalization()
const open = ref(false)
const anchor = useTemplateRef<HTMLElement | null>('anchor')
const textInput = useTemplateRef<{ inputRef?: HTMLInputElement } | null>('textInput')

const isDateTime = computed(() => isDateTimeGranularity(props.granularity))
const pickerIcon = computed(() =>
  isDateTime.value ? 'i-lucide-calendar-clock' : 'i-lucide-calendar',
)

/** ERPNext-style display pattern from System Settings (e.g. DD-MM-YYYY). */
const displayPattern = computed(() => localization.value.dateFormat || 'YYYY-MM-DD')

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function patternToken(date: DateValue) {
  return formatDateParts({ year: date.year, month: date.month, day: date.day })
}

const placeholderText = computed(() => patternToken(today(getLocalTimeZone())))

/** Shown text: formatted date when set, otherwise the raw draft while typing. */
const displayValue = computed(() => {
  if (props.modelValue) {
    const parsed = parsePickerValue(props.modelValue, isDateTime.value)
    if (parsed) {
      const datePart = patternToken(parsed)
      if (!isDateTime.value) return datePart
      return `${datePart} ${formatTime(props.modelValue, '')}`.trim()
    }
  }
  return String(props.modelValue ?? '')
})

const dateValue = computed({
  get: () => parsePickerValue(props.modelValue, isDateTime.value),
  set: (value: DateValue | null | undefined) => {
    emit('update:modelValue', serializePickerValue(value))
  },
})

/** Draft holds raw keystrokes while focused so typing is not snapped back. */
const focused = ref(false)
const draft = ref('')

const inputValue = computed(() =>
  focused.value ? draft.value : displayValue.value,
)

function onFocus() {
  draft.value = displayValue.value
  focused.value = true
  textInput.value?.inputRef?.select()
}

function onBlur() {
  focused.value = false
  draft.value = ''
}

/** Accept free-typed dates in the configured pattern (or ISO) plus HH:mm for datetime. */
function commitText(raw: string) {
  const text = raw.trim()
  if (!text) {
    draft.value = ''
    emit('update:modelValue', '')
    return
  }
  draft.value = raw

  const timeMatch = text.match(/[T\s](\d{1,2}):(\d{2})$/)
  const time = timeMatch
    ? { hour: Number(timeMatch[1]), minute: Number(timeMatch[2]) }
    : null
  const datePart = (time && timeMatch?.index != null ? text.slice(0, timeMatch.index) : text).trim()

  const iso = datePart.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/)
  const dmy = datePart.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/)
  const mdy = displayPattern.value === 'MM/DD/YYYY'
    ? datePart.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/)
    : null

  let base: { y: number, m: number, d: number } | null = null
  if (iso) base = { y: Number(iso[1]), m: Number(iso[2]), d: Number(iso[3]) }
  else if (dmy && displayPattern.value !== 'MM/DD/YYYY') base = { y: Number(dmy[3]), m: Number(dmy[2]), d: Number(dmy[1]) }
  else if (mdy) base = { y: Number(mdy[3]), m: Number(mdy[1]), d: Number(mdy[2]) }

  if (!base || base.m < 1 || base.m > 12 || base.d < 1 || base.d > 31) return

  if (isDateTime.value) {
    const hour = time ? Math.min(23, time.hour) : 0
    const minute = time ? time.minute : 0
    emit('update:modelValue', `${base.y}-${pad(base.m)}-${pad(base.d)}T${pad(hour)}:${pad(minute)}`)
    return
  }
  emit('update:modelValue', `${base.y}-${pad(base.m)}-${pad(base.d)}`)
}

function commitPicker(value: DateValue | undefined | null) {
  if (!value) return
  focused.value = false
  draft.value = ''
  dateValue.value = value
  if (!isDateTime.value) open.value = false
}

</script>

<template>
  <div
    ref="anchor"
    class="relative min-w-0"
    :class="[props.class || 'w-full']"
  >
    <UInput
      ref="textInput"
      :model-value="inputValue"
      :disabled="disabled"
      :required="required"
      :size="size"
      :placeholder="placeholderText"
      class="w-full min-w-0"
      autocomplete="off"
      @update:model-value="commitText"
      @focus="onFocus"
      @blur="onBlur"
    >
      <template #trailing>
        <UPopover
          v-model:open="open"
          :reference="anchor ?? undefined"
          :content="datePickerPopoverContent"
        >
          <UButton
            :icon="pickerIcon"
            color="neutral"
            variant="ghost"
            size="xs"
            square
            class="text-muted hover:text-highlighted"
            :aria-label="isDateTime ? 'Select date and time' : 'Select a date'"
            :disabled="disabled"
          />
          <template #content>
            <CommonAppDatePickerPopover
              :model-value="dateValue"
              mode="single"
              :months="1"
              :granularity="granularity"
              :disabled="disabled"
              @update:model-value="commitPicker"
            />
          </template>
        </UPopover>
      </template>
    </UInput>
  </div>
</template>
