<script setup lang="ts">
import type { ExportFieldOption, ExportRequest, ExportScope } from '~/types/stock-pos/export'

const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(defineProps<{
  fields?: ExportFieldOption[]
  selectedCount?: number
  loading?: boolean
}>(), {
  fields: () => [],
  selectedCount: 0,
  loading: false,
})

const emit = defineEmits<{
  submit: [request: ExportRequest]
}>()

const { t } = useI18n()
const startDate = ref('')
const endDate = ref('')
const scope = ref<ExportScope>('all_matching')
const selectedFields = ref<string[]>([])

const scopeItems = computed(() => [
  { label: t('core.exportDialog.allMatching'), value: 'all_matching' },
  { label: t('core.exportDialog.currentPage'), value: 'current_page' },
  {
    label: t('core.exportDialog.selectedRows', { n: props.selectedCount }),
    value: 'selected',
    disabled: props.selectedCount < 1,
  },
])

const invalidRange = computed(() => Boolean(
  startDate.value && endDate.value && startDate.value > endDate.value,
))
const noFields = computed(() => props.fields.length > 0 && selectedFields.value.length === 0)
const canSubmit = computed(() => !invalidRange.value && !noFields.value && !props.loading)

watch(open, (isOpen) => {
  if (!isOpen) return
  startDate.value = ''
  endDate.value = ''
  scope.value = 'all_matching'
  selectedFields.value = props.fields.map(field => field.value)
})

watch(() => props.selectedCount, (count) => {
  if (count < 1 && scope.value === 'selected') scope.value = 'all_matching'
})

function toggleField(value: string, checked: boolean | 'indeterminate') {
  selectedFields.value = checked === true
    ? [...new Set([...selectedFields.value, value])]
    : selectedFields.value.filter(field => field !== value)
}

function submit() {
  if (!canSubmit.value) return
  emit('submit', {
    startDate: startDate.value || undefined,
    endDate: endDate.value || undefined,
    scope: scope.value,
    fieldCodes: [...selectedFields.value],
  })
}
</script>

<template>
  <UModal
    v-model:open="open"
    :title="$t('core.exportDialog.title')"
    :description="$t('core.exportDialog.description')"
    :dismissible="false"
    :close="{ color: 'primary', variant: 'outline', class: 'rounded-full' }"
    :ui="{ content: 'w-[calc(100%-2rem)] max-w-2xl sm:max-w-2xl' }"
  >
    <template #body>
      <div class="space-y-5">
        <UFormField
          :label="$t('core.exportDialog.dateRange')"
          :help="$t('core.exportDialog.dateRangeHelp')"
          :error="invalidRange ? $t('core.exportDialog.invalidRange') : undefined"
        >
          <CommonAppDateRangeFilter
            v-model:start="startDate"
            v-model:end="endDate"
            inline
            class="w-full"
          />
        </UFormField>

        <UFormField :label="$t('core.exportDialog.scope')" :help="$t('core.exportDialog.scopeHelp')">
          <USelect
            v-model="scope"
            :items="scopeItems"
            value-key="value"
            class="w-full"
          />
        </UFormField>

        <fieldset v-if="fields.length" class="rounded-sm border border-default p-3">
          <legend class="px-1 text-sm font-medium text-highlighted">
            {{ $t('core.exportDialog.fields') }}
          </legend>
          <p class="mb-3 text-xs text-muted">{{ $t('core.exportDialog.fieldsHint') }}</p>
          <div class="grid gap-2 sm:grid-cols-2">
            <UCheckbox
              v-for="field in fields"
              :key="field.value"
              :model-value="selectedFields.includes(field.value)"
              :label="field.label"
              @update:model-value="toggleField(field.value, $event)"
            />
          </div>
          <p v-if="noFields" class="mt-2 text-xs text-error">
            {{ $t('core.exportDialog.fieldRequired') }}
          </p>
        </fieldset>
      </div>
    </template>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
color="neutral"
variant="ghost"
:disabled="loading"
@click="open = false">
          {{ $t('actions.cancel') }}
        </UButton>
        <UButton
icon="i-lucide-download"
:loading="loading"
:disabled="!canSubmit"
@click="submit">
          {{ $t('actions.export') }}
        </UButton>
      </div>
    </template>
  </UModal>
</template>
