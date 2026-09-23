<script setup lang="ts">
import type {
  ConnectionStatusFieldValue,
  DocumentFieldSchema,
  FieldOption,
} from '~/types/stock-pos/common'
import type { ConnectionStatus, NotificationRule } from '~/types/stock-pos/settings'
import type { AppRolePermissionRow } from '~/types/stock-pos/entities'
import { resolveFieldHelp } from '~/utils/field-help'
import { normalizeDocumentSequenceType } from '~/utils/document-sequences'
import { useReferenceOptions } from '~/composables/common/useReferenceOptions'
import { useFormErrors } from '~/composables/useFormErrors'
import type { ModuleRelated, ModuleTable } from '~/config/modules'
import type { AppRecord } from '~/config/admin-seed'
import { asNumber } from '~/composables/module/useModule'
import { isMoneyKey } from '~/utils/module/field-keys'
import { useCurrencyRateDialog } from '~/composables/common/useCurrencyRateDialog'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'
import {
  moduleDocumentLineActionKey,
  moduleDocumentRecordKey,
} from '~/utils/module/document-tabs'

const props = defineProps<{
  field: DocumentFieldSchema
  modelValue: unknown
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [unknown]
}>()

const { t, te } = useI18n()
const { loadReferenceOptions } = useReferenceOptions()
// Registers this form as an inline field-error sink, claims this field's key
// so its error can render inline, and reads the published backend
// `field_errors` per field key (snake/camel normalized).
const { errorFor, claim } = useFormErrors()
if (props.field.key) claim(props.field.key)

const hintOpen = ref(false)

const stringValue = computed({
  get: () => String(props.modelValue ?? ''),
  set: (v: string) => emit('update:modelValue', v),
})

const selectValue = computed({
  get: () => {
    if (props.modelValue == null || props.modelValue === '') return undefined
    if (typeof props.modelValue === 'object' && 'value' in (props.modelValue as object)) {
      const nested = (props.modelValue as { value?: unknown }).value
      return nested == null || nested === '' ? undefined : String(nested)
    }
    return String(props.modelValue)
  },
  set: (v: string | { value?: string } | undefined) => {
    if (v && typeof v === 'object' && 'value' in v) {
      emit('update:modelValue', v.value ?? '')
      return
    }
    emit('update:modelValue', v ?? '')
  },
})

const numberValue = computed({
  get: () => (typeof props.modelValue === 'number' ? props.modelValue : Number(props.modelValue || 0)),
  set: (v: number | null) => emit('update:modelValue', v ?? 0),
})

const boolValue = computed({
  get: () => {
    const trueValue = props.field.meta?.trueValue
    if (trueValue !== undefined) return props.modelValue === trueValue || props.modelValue === true
    if (typeof props.modelValue === 'string') {
      const value = props.modelValue.trim().toLowerCase()
      if (['no', 'false', '0', ''].includes(value)) return false
      if (['yes', 'true', '1'].includes(value)) return true
    }
    return Boolean(props.modelValue)
  },
  set: (v: boolean | 'indeterminate') => {
    const checked = v === true
    const trueValue = props.field.meta?.trueValue
    const falseValue = props.field.meta?.falseValue
    if (trueValue !== undefined) {
      emit('update:modelValue', checked ? trueValue : (falseValue ?? ''))
      return
    }
    emit('update:modelValue', checked)
  },
})

const multiValue = computed({
  get: () => (Array.isArray(props.modelValue)
    ? props.modelValue.map(String).filter(Boolean)
    : (props.modelValue ? [String(props.modelValue)] : [])),
  set: (v: string | string[]) => emit('update:modelValue', v),
})

const permissionRows = computed({
  get: () => (Array.isArray(props.modelValue) ? props.modelValue as AppRolePermissionRow[] : []),
  set: (v: AppRolePermissionRow[]) => emit('update:modelValue', v),
})

const csvValue = computed({
  get: () => Array.isArray(props.modelValue)
    ? (props.modelValue as unknown[]).map(String).join(', ')
    : String(props.modelValue ?? ''),
  set: (v: string) => {
    emit(
      'update:modelValue',
      String(v || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean),
    )
  },
})

const imageValue = computed({
  get: () => (props.modelValue == null || props.modelValue === ''
    ? undefined
    : String(props.modelValue)),
  set: (v: string | undefined) => emit('update:modelValue', v),
})

const colorValue = computed({
  get: () => String(props.modelValue || '#2563eb'),
  set: (v: string) => emit('update:modelValue', v),
})

const secretValue = computed({
  get: () => String(props.modelValue ?? ''),
  set: (v: string) => emit('update:modelValue', v),
})

const rulesValue = computed({
  get: () => (Array.isArray(props.modelValue) ? props.modelValue as NotificationRule[] : []),
  set: (v: NotificationRule[]) => emit('update:modelValue', v),
})

const connectionValue = computed(() => {
  const raw = props.modelValue as ConnectionStatusFieldValue | null | undefined
  return {
    status: (raw?.status || 'not_tested') as ConnectionStatus,
    message: raw?.message,
    lastTestedAt: raw?.lastTestedAt,
    details: raw?.details,
  }
})

const remoteOptions = ref<FieldOption[]>([])
const optionsPending = ref(false)
/** Last full (unfiltered) option list — keeps the selected label resolvable. */
const allOptions = ref<FieldOption[]>([])

const resolvedOptionsEndpoint = computed(() => props.field.optionsEndpoint || undefined)

watch(resolvedOptionsEndpoint, async (endpoint) => {
  remoteOptions.value = []
  allOptions.value = []
  if (!endpoint) return
  optionsPending.value = true
  try {
    const loaded = await loadReferenceOptions(endpoint)
    allOptions.value = loaded
    remoteOptions.value = loaded
  }
  catch {
    remoteOptions.value = []
  }
  finally {
    optionsPending.value = false
  }
}, { immediate: true })

const searchRemoteOptions = useDebounceFn(async (search: string) => {
  const endpoint = resolvedOptionsEndpoint.value
  if (!endpoint) return
  const term = String(search ?? '').trim()
  // Clearing the search restores the full list.
  if (!term) {
    remoteOptions.value = allOptions.value
    return
  }
  // The combobox echoes the selected id as its search term (e.g. a UUID);
  // searching for it would wipe the list and leave the raw id on screen.
  if (term === String(props.modelValue ?? '')) return
  optionsPending.value = true
  try {
    const loaded = await loadReferenceOptions(endpoint, term)
    // Keep the selected option available so its label still renders.
    const selected = allOptions.value.find(o => o.value === String(props.modelValue ?? ''))
    remoteOptions.value = selected && !loaded.some(o => o.value === selected.value)
      ? [selected, ...loaded]
      : loaded
  }
  finally { optionsPending.value = false }
}, 250)

const selectItems = computed(() =>
  [...(props.field.options || []), ...remoteOptions.value]
    .filter(o => o.value !== '')
    .map(o => ({
      label: o.labelKey ? t(o.labelKey) : (o.label || o.value),
      value: o.value,
    })),
)

const creatableSelectItems = computed(() => selectItems.value)

function onCreateSelectItem(item: string) {
  const trimmed = normalizeDocumentSequenceType(item)
  if (!trimmed) return
  emit('update:modelValue', trimmed)
}

const labelText = computed(() => {
  if (props.field.labelKey && te(props.field.labelKey)) return t(props.field.labelKey)
  if (props.field.label) return props.field.label
  return props.field.labelKey || ''
})

const helpText = computed(() => {
  if (props.field.help) return props.field.help
  return resolveFieldHelp(props.field, labelText.value, t, te)
})

const hintText = computed(() => {
  if (props.field.hintKey && te(props.field.hintKey)) return t(props.field.hintKey)
  return helpText.value
})

const placeholderText = computed(() => {
  if (props.field.placeholder) return props.field.placeholder
  if (props.field.placeholderKey && te(props.field.placeholderKey)) {
    return t(props.field.placeholderKey)
  }
  return labelText.value
})

const isBoolean = computed(() => props.field.type === 'boolean')
const isPermissionMatrix = computed(() => props.field.type === 'permission-matrix')
const isSecret = computed(() => props.field.type === 'secret')
const isColor = computed(() => props.field.type === 'color')
const isImage = computed(() => props.field.type === 'image')
const isIcon = computed(() => props.field.type === 'icon')

const isNotificationRules = computed(() => props.field.type === 'notification-rules')
const isConnectionStatus = computed(() => props.field.type === 'connection-status')
const isAlert = computed(() => props.field.type === 'alert')
const isLineTable = computed(() => props.field.type === 'line-table')
const isRelatedRecords = computed(() => props.field.type === 'related-records')
const isUomConversions = computed(() => props.field.type === 'uom-conversions')
const isBatches = computed(() => props.field.type === 'batches')
const isProductBatches = computed(() => props.field.type === 'product-batches')
const isProductMovements = computed(() => props.field.type === 'product-movements')
const isProductBarcode = computed(() => props.field.type === 'product-barcode')
const isPartyHistory = computed(() =>
  props.field.type === 'party-sales-history' || props.field.type === 'party-purchase-history',
)
const isFile = computed(() => props.field.type === 'file')

const lineAction = inject(moduleDocumentLineActionKey, undefined)
const recordAccess = inject(moduleDocumentRecordKey, null)

/** System roles (Administrator) keep the locked `ALL_PAGES` full-access state. */
const isSystemRole = computed(() =>
  Boolean(recordAccess?.get?.('is_system') ?? recordAccess?.get?.('isSystem')),
)

/** Whole loaded record for the party ledger panels (id, name, phone…). */
const partyRecord = computed(() => (recordAccess?.get('__record') as AppRecord | null) ?? null)
const partyKind = computed<'customer' | 'supplier'>(
  () => (props.field.meta?.kind === 'supplier' ? 'supplier' : 'customer'),
)

const lineTable = computed(() => props.field.meta?.table as ModuleTable | undefined)
const lineRows = computed({
  get: () => (Array.isArray(props.modelValue) ? props.modelValue as Array<Record<string, unknown>> : []),
  set: (rows: Array<Record<string, unknown>>) => emit('update:modelValue', rows),
})
const relatedGroups = computed(() =>
  Array.isArray(props.modelValue)
    ? props.modelValue as Array<ModuleRelated & { rows: AppRecord[] }>
    : [],
)
const showPricingTotals = computed(() => Boolean(props.field.meta?.showPricingTotals))
const includeTaxTotal = computed(() => Boolean(props.field.meta?.includeTax))
/** Show Paid now / Outstanding rows under the totals (purchase-style footers). */
const showPaidRemaining = computed(() => Boolean(props.field.meta?.showPaidRemaining))
/** Editable Discount / Tax / Paid-now inputs inline in the totals footer. */
const editableTotals = computed(() =>
  Boolean(props.field.meta?.editableTotals) && !props.disabled && !props.field.readOnly)

function setMoney(key: string, value: number | null | undefined) {
  recordAccess?.set?.(key, value ?? 0)
}
const lineCompact = computed(() => Boolean(props.field.meta?.compact))
const lineViewOnly = computed(() => Boolean(props.field.meta?.viewOnly || props.field.readOnly))

/** Document currency for line tables that opt in (`meta.currencyToggle`).
 *  The USD/KHR toggle beside the table title edits the record's `currency`,
 *  which every money amount on the document is entered in. Switching to KHR
 *  opens the shared exchange-rate dialog; cancelling keeps the previous
 *  currency, confirming records the rate on the document (`exchangeRate`). */
const docCurrency = computed<'USD' | 'KHR' | undefined>(() => {
  const raw = recordAccess?.get('currency')
  return raw === 'KHR' ? 'KHR' : raw === 'USD' ? 'USD' : undefined
})

const docCurrencyState = computed<'USD' | 'KHR'>({
  get: () => (docCurrency.value === 'KHR' ? 'KHR' : 'USD'),
  set: value => recordAccess?.set?.('currency', value),
})

const docRateState = computed<number | undefined>({
  get: () => {
    const rate = Number(recordAccess?.get('exchangeRate'))
    return Number.isFinite(rate) && rate > 0 ? rate : undefined
  },
  set: value => recordAccess?.set?.('exchangeRate', value),
})

const {
  dialogOpen: currencyRateDialogOpen,
  toggle: toggleDocCurrency,
  confirm: confirmDocCurrency,
} = useCurrencyRateDialog({ currency: docCurrencyState, rate: docRateState })

function setDocCurrency(value: 'USD' | 'KHR') {
  toggleDocCurrency(value)
}

const { formatMoney } = useAppLocalization()

const documentCurrency = computed(() => String(recordAccess?.get('currency') || '').trim() || undefined)

/** A plain `number` field that stores money (gets the currency symbol suffix). */
const isMoneyField = computed(() => props.field.type === 'number' && isMoneyKey(props.field.key))

function moneyAmount(key: string) {
  return asNumber(recordAccess?.get(key))
}

function moneyLabel(value: unknown) {
  return formatMoney(value, documentCurrency.value)
}

function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  emit('update:modelValue', file?.name || props.modelValue)
}

const iconValue = computed({
  get: () => String(props.modelValue ?? ''),
  set: (v: string) => emit('update:modelValue', v),
})

/** Textareas: min 3 lines, grow with content up to 7. */
const TEXTAREA_MIN_ROWS = 3
const TEXTAREA_MAX_ROWS = 7

const textareaRows = computed(() => {
  const requested = props.field.rows ?? TEXTAREA_MIN_ROWS
  return Math.min(TEXTAREA_MAX_ROWS, Math.max(TEXTAREA_MIN_ROWS, requested))
})

function toggleHint() {
  hintOpen.value = !hintOpen.value
}

function closeHint() {
  hintOpen.value = false
}

watch(() => props.field.key, () => {
  hintOpen.value = false
})

</script>

<template>
  <CommonAppRolePermissionMatrix
    v-if="isPermissionMatrix"
    v-model="permissionRows"
    :disabled="disabled || field.readOnly"
    :system-role="isSystemRole"
  />

  <div
    v-else-if="isLineTable && lineTable"
    class="space-y-6 md:col-span-2"
  >
    <TableAppLineTable
      :table="lineTable"
      :model-value="lineRows"
      :disabled="disabled || lineViewOnly"
      :compact="lineCompact"
      :view-only-actions="lineViewOnly"
      :hide-add="Boolean(field.meta?.hideAdd)"
      :hide-row-actions="Boolean(field.meta?.hideRowActions)"
      :currency="field.meta?.currencyToggle ? docCurrency : undefined"
      @update:model-value="lineRows = $event"
      @update:currency="setDocCurrency"
      @row-action="(action, row) => lineAction?.(action, row)"
    />
    <p
      v-if="errorFor(field.key)"
      class="text-sm text-error"
    >
      {{ errorFor(field.key) }}
    </p>
    <CommonAppExchangeRateDialog
      v-if="field.meta?.currencyToggle"
      v-model:open="currencyRateDialogOpen"
      @confirm="confirmDocCurrency"
    />
    <div
      v-if="showPricingTotals"
      class="ms-auto grid w-full max-w-md gap-2.5 rounded-sm border border-default bg-elevated/50 p-4 text-sm"
    >
      <div class="flex items-center justify-between gap-6">
        <span class="text-muted">{{ $t('app.fields.subtotal') }}</span>
        <span class="font-medium text-highlighted tabular-nums">{{ moneyLabel(moneyAmount('subtotal')) }}</span>
      </div>
      <div class="flex items-center justify-between gap-6">
        <span class="text-muted">{{ $t('app.fields.discount') }}</span>
        <CommonAppMoneyField
          v-if="editableTotals"
          inline
          :model-value="moneyAmount('discount')"
          :currency="docCurrency"
          :min="0"
          :step="0.01"
          size="sm"
          align="right"
          class="w-32"
          :aria-label="$t('app.fields.discount')"
          @update:model-value="setMoney('discount', $event)"
        />
        <span
          v-else
          class="font-medium text-highlighted tabular-nums"
        >− {{ moneyLabel(moneyAmount('discount')) }}</span>
      </div>
      <div
        v-if="includeTaxTotal"
        class="flex items-center justify-between gap-6"
      >
        <span class="text-muted">{{ $t('app.fields.tax') }}</span>
        <CommonAppMoneyField
          v-if="editableTotals"
          inline
          :model-value="moneyAmount('tax')"
          :currency="docCurrency"
          :min="0"
          :step="0.01"
          size="sm"
          align="right"
          class="w-32"
          :aria-label="$t('app.fields.tax')"
          @update:model-value="setMoney('tax', $event)"
        />
        <span
          v-else
          class="font-medium text-highlighted tabular-nums"
        >{{ moneyLabel(moneyAmount('tax')) }}</span>
      </div>
      <div class="mt-1 flex items-center justify-between gap-6 border-t border-default pt-3 text-lg">
        <span class="font-semibold text-highlighted">{{ $t('app.fields.total') }}</span>
        <span class="font-bold text-primary tabular-nums">{{ moneyLabel(moneyAmount('total')) }}</span>
      </div>
      <template v-if="showPaidRemaining">
        <div class="flex items-center justify-between gap-6">
          <span class="text-muted">{{ $t('app.pos.paidNow') }}</span>
          <CommonAppMoneyField
            v-if="editableTotals"
            inline
            :model-value="moneyAmount('paidNow')"
            :currency="docCurrency"
            :min="0"
            :max="moneyAmount('total')"
            :step="0.01"
            size="sm"
            align="right"
            class="w-32"
            :aria-label="$t('app.pos.paidNow')"
            @update:model-value="setMoney('paidNow', $event)"
          />
          <span
            v-else
            class="font-medium text-highlighted tabular-nums"
          >{{ moneyLabel(moneyAmount('paidNow')) }}</span>
        </div>
        <div class="flex items-center justify-between gap-6">
          <span class="text-muted">{{ $t('app.pos.outstandingAmount') }}</span>
          <span class="font-medium text-highlighted tabular-nums">{{ moneyLabel(moneyAmount('remaining')) }}</span>
        </div>
      </template>
    </div>
  </div>

  <TableAppRelatedRecords
    v-else-if="isRelatedRecords"
    class="md:col-span-2"
    :groups="relatedGroups"
  />

  <StockPricingField
    v-else-if="isUomConversions"
    class="md:col-span-2 flex min-h-112 flex-1 flex-col"
    :model-value="modelValue"
    :disabled="disabled || field.readOnly"
    @update:model-value="emit('update:modelValue', $event)"
  />

  <!-- Product Batches tab: lots + Pricing active toggle. -->
  <StockBatchManagePanel
    v-else-if="isProductBatches"
    class="md:col-span-2 flex min-h-112 flex-1 flex-col"
    :product="(recordAccess?.get('__record') as AppRecord | null) ?? null"
    :disabled="disabled || field.readOnly"
  />

  <!-- Read-only batch lots of this product (legacy dialog panel). -->
  <StockBatchListPanel
    v-else-if="isBatches"
    class="md:col-span-2"
    :product="(recordAccess?.get('__record') as AppRecord | null) ?? null"
  />

  <!-- Read-only batch-traceable movements of this product (Movements tab). -->
  <StockProductMovementsPanel
    v-else-if="isProductMovements"
    class="md:col-span-2"
    :product="(recordAccess?.get('__record') as AppRecord | null) ?? null"
  />

  <!-- Barcode sticker preview + print sheet (Barcode tab). -->
  <StockProductBarcodePanel
    v-else-if="isProductBarcode"
    class="md:col-span-2"
    :product="(recordAccess?.get('__record') as AppRecord | null) ?? null"
    :disabled="disabled || field.readOnly"
  />

  <!-- Customer / Supplier detail History tab. -->
  <PartyHistoryPanel
    v-else-if="isPartyHistory"
    class="md:col-span-2"
    :party="partyRecord"
    :kind="partyKind"
  />

  <UAlert
    v-else-if="isAlert"
    class="md:col-span-2"
    :color="field.alertColor || 'warning'"
    variant="subtle"
    :title="labelText"
    :description="helpText || undefined"
  />

  <CommonAppSecretInput
    v-else-if="isSecret"
    v-model="secretValue"
    :label="labelText"
    :help="helpText"
    :disabled="disabled || field.readOnly"
  />

  <CommonAppColorPicker
    v-else-if="isColor"
    v-model="colorValue"
    :label="labelText"
    :help="helpText"
    :disabled="disabled || field.readOnly"
  />

  <CommonAppImageUploadField
    v-else-if="isImage"
    v-model="imageValue"
    :label="labelText"
    :help="helpText"
    :compact="Boolean(field.meta?.compact)"
    :folder="String(field.meta?.folder || 'products')"
    :disabled="disabled || field.readOnly"
  />

  <CommonAppIconPicker
    v-else-if="isIcon"
    v-model="iconValue"
    :label="labelText"
    :help="helpText"
    :disabled="disabled || field.readOnly"
  />

  <!-- Configuration builders removed (numbering-preview, validation, options, visibility, workflow) -->

  <div
    v-else-if="isNotificationRules"
    class="space-y-2 md:col-span-2"
  >
    <p class="text-sm font-medium">
      {{ t('core.settings.eventRules') }}
    </p>
    <div
      v-for="rule in rulesValue"
      :key="rule.id"
      class="flex items-center justify-between rounded-sm border border-default px-3 py-2"
    >
      <span class="text-sm">{{ rule.event }}</span>
      <USwitch v-model="rule.enabled" :disabled="disabled || field.readOnly" />
    </div>
  </div>

  <CommonAppConnectionStatusCard
    v-else-if="isConnectionStatus"
    class="md:col-span-2"
    :status="connectionValue.status"
    :title="labelText"
    :message="connectionValue.message"
    :last-tested-at="connectionValue.lastTestedAt"
    :details="connectionValue.details"
  />

  <!-- Checkbox: label beside control + helper text below -->
  <UFormField
    v-else-if="isBoolean"
    :error="errorFor(field.key)"
    :help="helpText"
  >
    <div class="flex min-h-11 flex-wrap items-center gap-2 pt-1">
      <UCheckbox
        v-model="boolValue"
        :disabled="disabled || field.readOnly"
        :required="field.required"
        size="md"
        :ui="{ label: 'text-base text-highlighted' }"
      >
        <template #label>
          <span class="inline-flex items-center gap-1.5">
            <span>{{ labelText }}</span>
            <UButton
              v-if="hintText"
              icon="i-lucide-info"
              color="neutral"
              variant="ghost"
              size="xs"
              square
              class="text-muted"
              :aria-label="hintText"
              @click.prevent.stop="toggleHint"
            />
          </span>
        </template>
      </UCheckbox>

      <div
        v-if="hintText && hintOpen"
        class="inline-flex max-w-md items-start gap-2 rounded-sm border border-default bg-elevated px-2.5 py-1.5 text-xs text-toned"
      >
        <p class="min-w-0 flex-1 leading-relaxed">{{ hintText }}</p>
        <UButton
          icon="i-lucide-x"
          color="neutral"
          variant="soft"
          size="xs"
          square
          class="shrink-0"
          @click="closeHint"
        />
      </div>
    </div>
  </UFormField>

  <!-- Standard fields: label + control + help below -->
  <UFormField
    v-else
    :label="labelText"
    :required="field.required"
    :error="errorFor(field.key)"
    :help="helpText"
  >
    <div class="flex items-start gap-1.5">
      <div class="min-w-0 flex-1">
        <UTextarea
          v-if="field.type === 'textarea'"
          v-model="stringValue"
          :disabled="disabled || field.readOnly"
          :placeholder="placeholderText"
          :rows="textareaRows"
          :maxrows="TEXTAREA_MAX_ROWS"
          autoresize
          size="md"
          class="w-full"
        />
        <CommonAppMoneyField
          v-else-if="isMoneyField"
          v-model="numberValue"
          inline
          :currency="documentCurrency"
          :disabled="disabled || field.readOnly"
          align="right"
          size="md"
          class="w-full"
        />
        <UInputNumber
          v-else-if="field.type === 'number'"
          v-model="numberValue"
          :disabled="disabled || field.readOnly"
          :increment="false"
          :decrement="false"
          size="md"
          class="w-full"
        />
        <CommonAppInputDate
          v-else-if="field.type === 'date'"
          v-model="stringValue"
          :disabled="disabled || field.readOnly"
          :required="field.required"
          size="md"
          class="w-full"
        />
        <CommonAppInputDate
          v-else-if="field.type === 'datetime'"
          v-model="stringValue"
          granularity="minute"
          :disabled="disabled || field.readOnly"
          :required="field.required"
          size="md"
          class="w-full"
        />
        <UInputMenu
          v-else-if="field.type === 'select' && field.meta?.creatable"
          v-model="selectValue"
          :items="creatableSelectItems"
          value-key="value"
          create-item
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          size="md"
          class="w-full"
          @create="onCreateSelectItem"
        />
        <USelectMenu
          v-else-if="field.type === 'select' && field.optionsEndpoint"
          v-model="selectValue"
          :items="selectItems"
          value-key="value"
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          :loading="optionsPending"
          :search-input="{ placeholder: placeholderText }"
          ignore-filter
          size="md"
          class="w-full"
          @update:search-term="searchRemoteOptions"
        />
        <USelect
          v-else-if="field.type === 'select'"
          v-model="selectValue"
          :items="selectItems"
          value-key="value"
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          :loading="optionsPending"
          size="md"
          class="w-full"
        />
        <CommonAppMentionMultiInput
          v-else-if="field.type === 'multiselect'"
          v-model="multiValue"
          :items="selectItems"
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          :loading="optionsPending"
          @search="searchRemoteOptions"
        />
        <UInput
          v-else-if="field.type === 'csv-list'"
          v-model="csvValue"
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          size="md"
          class="w-full"
        />
        <UInput
          v-else-if="isFile"
          type="file"
          :disabled="disabled || field.readOnly"
          size="md"
          class="w-full"
          @change="onFileChange"
        />
        <UInput
          v-else
          v-model="stringValue"
          :type="field.type === 'url' ? 'url' : 'text'"
          :placeholder="placeholderText"
          :disabled="disabled || field.readOnly"
          size="md"
          class="w-full"
        />
      </div>

      <UButton
        v-if="field.hintKey && hintText"
        icon="i-lucide-info"
        color="neutral"
        variant="ghost"
        size="xs"
        square
        class="mt-1.5 shrink-0 text-muted"
        @click="toggleHint"
      />
    </div>

    <div
      v-if="field.hintKey && hintText && hintOpen"
      class="mt-2 flex items-start gap-2 rounded-sm border border-default bg-elevated px-2.5 py-1.5 text-xs text-toned"
    >
      <p class="min-w-0 flex-1 leading-relaxed">{{ hintText }}</p>
      <UButton
        icon="i-lucide-x"
        color="neutral"
        variant="soft"
        size="xs"
        square
        class="shrink-0"
        @click="closeHint"
      />
    </div>
  </UFormField>
</template>
