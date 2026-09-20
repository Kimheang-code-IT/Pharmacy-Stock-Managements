<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import {
  BARCODE_LABEL_PRESETS,
  barcodeLabelCss,
  barcodeLabelHtml,
  DEFAULT_BARCODE_LABEL_SETTINGS,
  normalizeLabelSettings,
  printBarcodeLabels,
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

const SETTINGS_KEY = 'ui:barcode-label-settings'
/** CSS pixel size of one millimetre on screen at the browser's 96dpi. */
const PX_PER_MM = 96 / 25.4
const PREVIEW_MAX_W = 300
const PREVIEW_MAX_H = 240

type NumericSettingKey =
  | 'widthMm' | 'heightMm' | 'gapXMm' | 'gapYMm'
  | 'marginTopMm' | 'marginLeftMm' | 'barcodeHeightMm'
  | 'barcodeScale' | 'fontSizePt' | 'labelsPerRow'

/** Editable label-size fields (label = i18n suffix under `app.stock.`). */
const numericFields: Array<{
  key: NumericSettingKey
  label: string
  min: number
  max: number
  step: number
}> = [
  { key: 'widthMm', label: 'barcodeWidthMm', min: 10, max: 210, step: 1 },
  { key: 'heightMm', label: 'barcodeHeightMm', min: 8, max: 297, step: 1 },
  { key: 'gapXMm', label: 'barcodeGapXMm', min: 0, max: 50, step: 0.5 },
  { key: 'gapYMm', label: 'barcodeGapYMm', min: 0, max: 50, step: 0.5 },
  { key: 'marginTopMm', label: 'barcodeMarginTop', min: 0, max: 80, step: 1 },
  { key: 'marginLeftMm', label: 'barcodeMarginLeft', min: 0, max: 80, step: 1 },
  { key: 'barcodeHeightMm', label: 'barcodeBarcodeHeight', min: 3, max: 120, step: 0.5 },
  { key: 'barcodeScale', label: 'barcodeWidthScale', min: 30, max: 100, step: 5 },
  { key: 'fontSizePt', label: 'barcodeFontSize', min: 4, max: 24, step: 0.5 },
  { key: 'labelsPerRow', label: 'barcodeLabelsPerRow', min: 1, max: 20, step: 1 },
]

const settings = reactive<BarcodeLabelSettings>({ ...DEFAULT_BARCODE_LABEL_SETTINGS })
const customActive = ref(false)

const labelCss = barcodeLabelCss()

const barcode = computed(() => String(props.product?.barcode || '').trim())
const name = computed(() => String(props.product?.name || ''))

/** Stickers never print prices — force the price rows off regardless of any
 *  stored settings, so a label shows only the name, bars and code. */
const labelSettings = computed<BarcodeLabelSettings>(() => ({
  ...settings,
  showUsd: false,
  showKhr: false,
}))

const previewData = computed<BarcodeLabelData>(() => ({
  name: name.value,
  barcode: barcode.value,
  priceUsd: 0,
  priceKhr: null,
}))

const previewHtml = computed(() => barcodeLabelHtml(previewData.value, labelSettings.value))

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

const pageModeItems = computed(() => [
  { label: t('app.stock.barcodePageA4'), value: 'A4' },
  { label: t('app.stock.barcodePageLabel'), value: 'label' },
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
  if (!barcode.value || props.disabled) return
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
                <div v-html="previewHtml" />
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
              :disabled="disabled"
              @click="printStickers"
            />
          </div>
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

          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
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
            <label class="text-sm">
              <span class="mb-1 block text-muted">{{ t('app.stock.barcodePageMode') }}</span>
              <USelect
                v-model="settings.pageMode"
                :items="pageModeItems"
                value-key="value"
                class="w-full"
              />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-default pt-3">
            <label class="flex items-center gap-2 text-sm">
              <USwitch v-model="settings.showName" size="sm" />
              <span>{{ t('app.stock.barcodeShowName') }}</span>
            </label>
          </div>
        </div>
      </div>
    </template>

    <!-- Element CSS shared with the print document (keeps preview pixel-accurate). -->
    <component :is="'style'">{{ labelCss }}</component>
  </div>
</template>
