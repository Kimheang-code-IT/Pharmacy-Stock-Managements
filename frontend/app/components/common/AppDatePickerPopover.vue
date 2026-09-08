<script setup lang="ts">
import { CalendarDate, CalendarDateTime, Time, getLocalTimeZone, today } from '@internationalized/date'
import type { DateValue } from '@internationalized/date'
import type { DatePickerGranularity } from '~/utils/date-picker'
import {
  isDateTimeGranularity,
  mergeDateWithTime,
  toCalendarDate,
} from '~/utils/date-picker'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'
import { isHour12TimeFormat, timeFormatHasSeconds } from '~/utils/format/localization-config'

const props = withDefaults(defineProps<{
  mode?: 'single' | 'range'
  granularity?: DatePickerGranularity
  disabled?: boolean
  /** Number of month grids shown at once. */
  months?: number
}>(), {
  mode: 'single',
  granularity: 'day',
  months: 2,
})

/** Single date / datetime — shared with UInputDate v-model. */
const modelValue = defineModel<DateValue | undefined>()
/** Range — shared with UInputDate range v-model. */
const rangeValue = defineModel<{ start: DateValue, end: DateValue } | undefined>('rangeValue')

const { t } = useI18n()
const { localization } = useAppLocalization()

const calendarLocale = computed(() => localization.value.locale)
const weekStartsOn = computed(() => localization.value.firstDayOfWeek)
const hourCycle = computed(() => isHour12TimeFormat(localization.value.timeFormat) ? 12 : 24)
const timeGranularity = computed(() => timeFormatHasSeconds(localization.value.timeFormat) ? 'second' : 'minute')

const isDateTime = computed(() => isDateTimeGranularity(props.granularity))
const calendarSize = computed(() => 'xs' as const)

const initialPlaceholder = today(getLocalTimeZone())
const placeholder = ref(new CalendarDate(
  initialPlaceholder.year,
  initialPlaceholder.month,
  initialPlaceholder.day,
))
const placeholderBinding = computed({
  get: () => placeholder.value as unknown as DateValue,
  set: (value: DateValue | undefined) => {
    if (!value) return
    placeholder.value = new CalendarDate(value.year, value.month, value.day)
  },
})

const singleCalendar = computed({
  get: () => toCalendarDate(modelValue.value),
  set: (value: CalendarDate | undefined | null) => {
    if (!value) {
      modelValue.value = undefined
      return
    }
    if (isDateTime.value) {
      modelValue.value = mergeDateWithTime(value, modelValue.value)
      return
    }
    modelValue.value = value
  },
})

const rangeCalendar = computed({
  get() {
    if (props.mode !== 'range') return undefined
    const value = rangeValue.value
    if (!value?.start && !value?.end) return undefined

    if (!isDateTime.value) {
      return {
        start: toCalendarDate(value.start) ?? toCalendarDate(value.end)!,
        end: toCalendarDate(value.end) ?? toCalendarDate(value.start)!,
      }
    }

    return {
      start: toCalendarDate(value.start) ?? toCalendarDate(value.end)!,
      end: toCalendarDate(value.end) ?? toCalendarDate(value.start)!,
    }
  },
  set(value: { start: CalendarDate, end: CalendarDate } | null | undefined) {
    if (props.mode !== 'range') return
    if (!value?.start && !value?.end) {
      rangeValue.value = undefined
      return
    }

    const current = rangeValue.value
    if (isDateTime.value) {
      rangeValue.value = {
        start: mergeDateWithTime(value.start, current?.start, 0, 0),
        end: mergeDateWithTime(value.end ?? value.start, current?.end, 23, 59),
      }
      return
    }

    rangeValue.value = {
      start: value.start,
      end: value.end ?? value.start,
    }
  },
})

function readTimePart(value: DateValue | undefined, bound: 'start' | 'end') {
  if (value && 'hour' in value) {
    return { hour: value.hour, minute: value.minute }
  }
  return bound === 'end'
    ? { hour: 23, minute: 59 }
    : { hour: 0, minute: 0 }
}

function writeSingleTime(hour: number, minute: number) {
  const base = toCalendarDate(modelValue.value) || today(getLocalTimeZone())
  modelValue.value = new CalendarDateTime(base.year, base.month, base.day, hour, minute)
}

function writeRangeTime(bound: 'start' | 'end', hour: number, minute: number) {
  const current = rangeValue.value
  const source = bound === 'start' ? current?.start : current?.end
  const base = toCalendarDate(source) || today(getLocalTimeZone())
  const next = new CalendarDateTime(base.year, base.month, base.day, hour, minute)
  rangeValue.value = {
    start: bound === 'start' ? next : (current?.start ?? next),
    end: bound === 'end' ? next : (current?.end ?? next),
  }
}

const singleTime = computed({
  get: (): Time => {
    const { hour, minute } = readTimePart(modelValue.value, 'start')
    return new Time(hour, minute, 0)
  },
  set: (value: Time | null | undefined) => {
    if (!value) return
    writeSingleTime(value.hour, value.minute)
  },
})

const rangeStartTime = computed({
  get: (): Time => {
    const { hour, minute } = readTimePart(rangeValue.value?.start, 'start')
    return new Time(hour, minute, 0)
  },
  set: (value: Time | null | undefined) => {
    if (!value) return
    writeRangeTime('start', value.hour, value.minute)
  },
})

const rangeEndTime = computed({
  get: (): Time => {
    const { hour, minute } = readTimePart(rangeValue.value?.end, 'end')
    return new Time(hour, minute, 0)
  },
  set: (value: Time | null | undefined) => {
    if (!value) return
    writeRangeTime('end', value.hour, value.minute)
  },
})

function goToday() {
  const now = today(getLocalTimeZone())
  placeholder.value = new CalendarDate(now.year, now.month, now.day)

  if (props.mode === 'single') {
    if (isDateTime.value) {
      const date = new Date()
      modelValue.value = new CalendarDateTime(
        now.year,
        now.month,
        now.day,
        date.getHours(),
        date.getMinutes(),
      )
      return
    }
    modelValue.value = now
    return
  }

  if (isDateTime.value) {
    const date = new Date()
    rangeValue.value = {
      start: new CalendarDateTime(now.year, now.month, now.day, 0, 0),
      end: new CalendarDateTime(now.year, now.month, now.day, date.getHours(), date.getMinutes()),
    }
    return
  }

  rangeValue.value = { start: now, end: now }
}

/** Day-only range: bind UCalendar directly to rangeValue (Nuxt UI pattern). */
const dayRangeCalendar = computed({
  get: () => rangeValue.value as { start: CalendarDate, end: CalendarDate } | undefined,
  set: (value: { start: CalendarDate, end: CalendarDate } | undefined) => {
    rangeValue.value = value
  },
})
</script>

<template>
  <div class="w-full max-w-136">
    <UCalendar
      v-if="mode === 'single'"
      v-model="singleCalendar"
      v-model:placeholder="placeholderBinding"
      class="p-2"
      :number-of-months="months"
      :paged-navigation="true"
      :size="calendarSize"
      :disabled="disabled"
      :locale="calendarLocale"
      :week-starts-on="weekStartsOn"
    />
    <UCalendar
      v-else-if="!isDateTime"
      v-model="dayRangeCalendar"
      v-model:placeholder="placeholderBinding"
      class="p-2"
      range
      :number-of-months="2"
      :paged-navigation="true"
      :size="calendarSize"
      :disabled="disabled"
      :locale="calendarLocale"
      :week-starts-on="weekStartsOn"
    />
    <UCalendar
      v-else
      v-model="rangeCalendar"
      v-model:placeholder="placeholderBinding"
      class="p-2"
      range
      :number-of-months="2"
      :paged-navigation="true"
      :size="calendarSize"
      :disabled="disabled"
      :locale="calendarLocale"
      :week-starts-on="weekStartsOn"
    />

    <div
      class="flex flex-wrap items-end gap-2 border-t border-default px-2 pb-2 pt-2"
      :class="isDateTime ? 'justify-between' : 'justify-end'"
    >
      <UInputTime
        v-if="isDateTime && mode === 'single'"
        v-model="singleTime"
        color="neutral"
        variant="outline"
        size="sm"
        :disabled="disabled"
        :locale="calendarLocale"
        :hour-cycle="hourCycle"
        :granularity="timeGranularity"
        class="min-w-0 flex-1"
      />
      <div
        v-else-if="isDateTime && mode === 'range'"
        class="flex min-w-0 flex-1 flex-wrap items-end gap-3"
      >
        <div class="min-w-34 flex-1 space-y-1">
          <label class="block text-xs font-medium text-muted">
            {{ t('core.common.startTime') }}
          </label>
          <UInputTime
            v-model="rangeStartTime"
            color="neutral"
            variant="outline"
            size="sm"
            :disabled="disabled"
            :locale="calendarLocale"
            :hour-cycle="hourCycle"
            :granularity="timeGranularity"
            class="w-full"
          />
        </div>
        <div class="min-w-34 flex-1 space-y-1">
          <label class="block text-xs font-medium text-muted">
            {{ t('core.common.endTime') }}
          </label>
          <UInputTime
            v-model="rangeEndTime"
            color="neutral"
            variant="outline"
            size="sm"
            :disabled="disabled"
            :locale="calendarLocale"
            :hour-cycle="hourCycle"
            :granularity="timeGranularity"
            class="w-full"
          />
        </div>
      </div>

      <UButton
        color="neutral"
        variant="outline"
        class="shrink-0 justify-center"
        size="sm"
        :disabled="disabled"
        @click="goToday"
      >
        {{ t('core.common.today') }}
      </UButton>
    </div>
  </div>
</template>
