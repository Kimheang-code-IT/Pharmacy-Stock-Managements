<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import {
  BARCODE_LABEL_PRESETS,
  barcodeLabelCss,
  barcodeLabelHtml,
  barcodePrintState,
  DEFAULT_BARCODE_LABEL_SETTINGS,
  fitBarcodeLabelNames,
  normalizeLabelSettings,
  printBarcodeLabels,
  recommendBarcodeLabelPreset,
  type BarcodeLabelData,
  type BarcodeLabelSettings,
} from '~/utils/print/barcode-label'

/**
 * Product document **Barcode** tab: preview a CODE128 sticker and print it.
 * Every sticker dimension is user-editable in millimetres, so the same settings
 * drive A4 sticker sheets and thermal label printers. The preview re-renders on
 * every change and the print CSS uses the raw millimetre values.
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
  disabled?: boolean
}>(), {
  product: null,
  disabled: false,
})

const { t } = useI18n()

const SETTINGS_KEY = 'ui:barcode-label-settings:v3'
/** CSS pixel size of one millimetre on screen at the browser's 96dpi. */
const PX_PER_MM = 96 / 25.4
const PREVIEW_MAX_W = 300
const PREVIEW_MAX_H = 240

type NumericSettingKey = 'widthMm' | 'heightMm'

/**
 * The panel only exposes the sticker size. Everything else (gaps, margins,
 * font, page mode, content toggles) is fixed so one sheet layout always prints
 * at a size the scanner can read.
 */
const FIXED_LABEL_SETTINGS: Partial<BarcodeLabelSettings> = {
  gapXMm: 2,
  gapYMm: 2,
  marginTopMm: 8,
  marginLeftMm: 8,
  barcodeAutoFit: true,
  fontSizePt: 8,
  showKhr: false,
  labelsPerRow: 4,
}

/** Editable label-size fields (label = i18n suffix under `app.stock.`). */
const numericFields: Array<{
  key: NumericSettingKey
  label: string
  min: number
  max: number
  step: number
}> = [
  { key: 'widthMm', label: 'barcodeWidthMm', min: 20, max: 210, step: 1 },
  { key: 'heightMm', label: 'barcodeHeightMm', min: 15, max: 297, step: 1 },
]

const settings = reactive<BarcodeLabelSettings>({ ...DEFAULT_BARCODE_LABEL_SETTINGS })
const customActive = ref(false)

const labelCss = barcodeLabelCss()

const barcode = computed(() => String(props.product?.barcode || '').trim())
const name = computed(() => String(props.product?.name || ''))

/** Sticker size is user-chosen; every other setting is fixed (see above). */
const labelSettings = computed<BarcodeLabelSettings>(() =>
  normalizeLabelSettings({ ...settings, ...FIXED_LABEL_SETTINGS }))

/** Product sale price (USD) printed on the sticker when "Show price" is on. */
const previewData = computed<BarcodeLabelData>(() => ({
  name: name.value,
  barcode: barcode.value,
  priceUsd: Number(props.product?.salePrice ?? 0),
  priceKhr: null,
}))

/** Keep the button, warning, and click guard on the exact layout used to print. */
const printState = computed(() => barcodePrintState(barcode.value, labelSettings.value, props.disabled))
const tooDense = computed(() => printState.value.layout.tooDense)
const suggestedWidthMm = computed(() => printState.value.layout.minimumLabelWidthMm)
const printDisabled = computed(() => printState.value.disabled)
const recommendedPreset = computed(() => recommendBarcodeLabelPreset(barcode.value, labelSettings.value))

/** Preview the exact module layout already calculated for validation/printing. */
const previewHtml = computed(() =>
  barcodeLabelHtml(previewData.value, labelSettings.value, printState.value.layout))

/**
 * Auto-fit the product name inside the preview after every (re)render, using the
 * same routine as printing, so long names are shown in full — not truncated.
 */
const previewRef = ref<HTMLElement | null>(null)

function fitPreviewName() {
  if (previewRef.value) fitBarcodeLabelNames(previewRef.value)
}

watch(previewHtml, async () => {
  await nextTick()
  fitPreviewName()
}, { immediate: true })

onMounted(fitPreviewName)

/** Thermal printer resolution choices (the module width snaps to this grid). */
const dpiItems = [
  { label: '203 DPI', value: 203 },
  { label: '300 DPI', value: 300 },
  { label: '600 DPI', value: 600 },
]

const previewScale = computed(() => {
  const width = settings.widthMm * PX_PER_MM
  const height = settings.heightMm * PX_PER_MM
  return Math.min(1, PREVIEW_MAX_W / width, PREVIEW_MAX_H / height)
})

const previewBoxStyle = computed(() => ({
  width: `${Math.round(settings.widthMm * PX_PER_MM * previewScale.value)}px`,
  height: `${Math.round(settings.heightMm * PX_PER_MM * previewScale.value)}px`,
}))

const activePresetId = computed(() => BARCODE_LABEL_PRESETS
  .find(preset => preset.widthMm === settings.widthMm && preset.heightMm === settings.heightMm)?.id || 'custom')

/** Print target: one sticker per label (thermal) or a page of stickers (A4). */
const pageModeItems = computed(() => [
  { label: t('app.stock.barcodePageLabel'), value: 'label' },
  { label: t('app.stock.barcodePageA4'), value: 'A4' },
])

function applyPreset(preset: typeof BARCODE_LABEL_PRESETS[number]) {
  customActive.value = false
  settings.widthMm = preset.widthMm
  settings.heightMm = preset.heightMm
}

function chooseCustom() {
  customActive.value = true
}

function loadSettings() {
  if (!import.meta.client) return
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) Object.assign(settings, normalizeLabelSettings(JSON.parse(raw) as Partial<BarcodeLabelSettings>))
  }
  catch {
    // corrupt/legacy payload — keep defaults
  }
}

watch(settings, () => {
  if (!import.meta.client) return
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings }))
}, { deep: true })

onMounted(loadSettings)

function printStickers() {
  if (printDisabled.value) return
  void printBarcodeLabels([{ ...previewData.value }], labelSettings.value)
}
</script>

<template>
  <div class="flex min-w-0 flex-1 flex-col gap-4">
    <p v-if="!barcode" class="text-sm text-warning">{{ t('app.stock.barcodeEmpty') }}</p>

    <template v-else>
      <div class="flex flex-col gap-5 xl:flex-row xl:items-start">
        <!-- Preview + content + actions -->
        <div class="flex flex-col gap-4 xl:w-80 xl:shrink-0">
          <div class="flex flex-col items-center gap-2">
            <div
              class="flex items-center justify-center overflow-hidden rounded-sm border border-dashed border-default bg-white shadow-sm"
              :style="previewBoxStyle"
            >
              <div :style="{ transform: `scale(${previewScale})`, transformOrigin: 'top left' }">
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div ref="previewRef" v-html="previewHtml" />
              </div>
            </div>
            <p class="text-[11px] text-muted">
              {{ settings.widthMm }} × {{ settings.heightMm }} mm · {{ t('app.stock.barcodePreview') }}
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <UButton
              color="primary"
              icon="i-lucide-printer"
              :label="t('app.stock.barcodePrint')"
              :disabled="printDisabled"
              @click="printStickers"
            />
          </div>

          <p v-if="tooDense" class="text-xs text-warning">
            {{ t('app.stock.barcodeTooDense', { width: suggestedWidthMm }) }}
            <span v-if="recommendedPreset">
              {{ t('app.stock.barcodePresetRecommended', { preset: recommendedPreset.label }) }}
            </span>
          </p>
        </div>

        <!-- Label size settings -->
        <div class="flex min-w-0 flex-1 flex-col gap-4 rounded-sm border border-default p-4">
          <h3 class="text-sm font-semibold">{{ t('app.stock.barcodeSettingsTitle') }}</h3>

          <div class="flex flex-wrap items-center gap-2">
            <UButton
              v-for="preset in BARCODE_LABEL_PRESETS"
              :key="preset.id"
              size="xs"
              :color="!customActive && activePresetId === preset.id ? 'primary' : 'neutral'"
              :variant="!customActive && activePresetId === preset.id ? 'solid' : 'subtle'"
              :label="preset.label"
              @click="applyPreset(preset)"
            />
            <UButton
              size="xs"
              :color="customActive || activePresetId === 'custom' ? 'primary' : 'neutral'"
              :variant="customActive || activePresetId === 'custom' ? 'solid' : 'subtle'"
              icon="i-lucide-pencil-ruler"
              :label="t('app.stock.barcodePresetCustom')"
              @click="chooseCustom"
            />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label
              v-for="field in numericFields"
              :key="field.key"
              class="text-sm"
            >
              <span class="mb-1 block text-muted">{{ t(`app.stock.${field.label}`) }}</span>
              <UInput
                v-model.number="settings[field.key]"
                type="number"
                :min="field.min"
                :max="field.max"
                :step="field.step"
                class="w-full"
              />
            </label>
          </div>

          <UCheckbox
            v-model="settings.showName"
            :label="t('app.stock.barcodeShowName')"
          />

          <UCheckbox
            v-model="settings.showUsd"
            :label="t('app.stock.barcodeShowUsd')"
          />

          <div class="grid grid-cols-2 gap-3">
            <label class="text-sm">
              <span class="mb-1 block text-muted">{{ t('app.stock.barcodePageMode') }}</span>
              <USelect
                v-model="settings.pageMode"
                :items="pageModeItems"
                value-key="value"
                class="w-full"
              />
            </label>
            <label class="text-sm">
              <span class="mb-1 block text-muted">{{ t('app.stock.barcodePrinterDpi') }}</span>
              <USelect
                v-model="settings.printerDpi"
                :items="dpiItems"
                value-key="value"
                class="w-full"
              />
            </label>
          </div>

          <p class="text-[11px] text-muted">
            {{ t('app.stock.barcodeSizeHint') }}
          </p>
        </div>
      </div>
    </template>

    <!-- Element CSS shared with the print document (keeps preview pixel-accurate). -->
    <component :is="'style'">{{ labelCss }}</component>
  </div>
</template>
