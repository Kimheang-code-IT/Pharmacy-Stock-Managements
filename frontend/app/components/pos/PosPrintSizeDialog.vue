<script setup lang="ts">
import type { PrintCurrencyChoice } from '~/utils/print/invoice'
import type { PrintPaperSize } from '~/utils/print/html'

/**
 * Document print chooser shown right after a successful POS Submit (spec: no
 * invoice preview dialog — sale completes, the cashier picks A4 or A5, the
 * bilingual invoice prints through the hidden-iframe print document).
 * Also offers a print-currency switch (USD/KHR, defaulting to the record
 * currency); switching requires an exchange rate (1 USD = ? KHR) that is
 * printed in the document meta block. Closing/cancel skips printing; the
 * sale is already saved.
 */
const props = defineProps<{
  /** Currency the document was recorded in (default USD). */
  documentCurrency?: string
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  confirm: [size: PrintPaperSize, options: PrintCurrencyChoice]
}>()

const { t } = useI18n()

/** Two options only; A4 is the default choice (listed/emphasized first). */
const paperOptions: Array<{ value: PrintPaperSize, icon: string, labelKey: string, primary?: boolean }> = [
  { value: 'A4', icon: 'i-lucide-file-text', labelKey: 'app.pos.paperA4', primary: true },
  { value: 'A5', icon: 'i-lucide-file', labelKey: 'app.pos.paperA5' },
]

const currencyOptions = [
  { value: 'USD', icon: 'i-lucide-dollar-sign', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR', icon: 'i-lucide-banknote', labelKey: 'app.pos.currencyKhr' },
] as const

const recordCurrency = computed(() => props.documentCurrency || 'USD')
const printCurrency = ref<string>(recordCurrency.value)
const exchangeRateInput = ref('')

// Reset to the record currency each time the chooser reopens (new sale).
watch(open, (isOpen) => {
  if (isOpen) {
    printCurrency.value = recordCurrency.value
    exchangeRateInput.value = ''
  }
})

const converting = computed(() => printCurrency.value !== recordCurrency.value)

/** Rate must be a positive number whenever the print currency differs. */
const parsedRate = computed(() => Number(exchangeRateInput.value))
const rateValid = computed(() => !converting.value || (Number.isFinite(parsedRate.value) && parsedRate.value > 0))

function choose(size: PrintPaperSize) {
  if (!rateValid.value) return
  open.value = false
  emit('confirm', size, {
    currency: printCurrency.value,
    exchangeRate: converting.value ? parsedRate.value : undefined,
  })
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.pos.printSizeTitle')"
    icon="i-lucide-printer"
    size="sm"
  >
    <div class="flex flex-col gap-3">
      <div>
        <p class="mb-1.5 text-sm font-medium text-highlighted">
          {{ t('app.pos.printCurrency') }}
        </p>
        <div class="grid grid-cols-2 gap-2">
          <UButton
            v-for="option in currencyOptions"
            :key="option.value"
            :color="printCurrency === option.value ? 'primary' : 'neutral'"
            :variant="printCurrency === option.value ? 'solid' : 'outline'"
            size="lg"
            :icon="option.icon"
            :label="t(option.labelKey)"
            class="justify-center"
            @click="printCurrency = option.value"
          />
        </div>
      </div>

      <div v-if="converting">
        <label class="mb-1.5 block text-sm font-medium text-highlighted" for="pos-exchange-rate">
          {{ t('app.pos.exchangeRate') }}
        </label>
        <UInput
          id="pos-exchange-rate"
          v-model="exchangeRateInput"
          type="number"
          size="lg"
          min="0"
          step="1"
          icon="i-lucide-arrow-left-right"
          :placeholder="t('app.pos.exchangeRatePlaceholder')"
          class="w-full"
          @keydown.enter.prevent="choose('A4')"
        />
        <p v-if="!rateValid" class="mt-1 text-xs text-error">
          {{ t('app.pos.exchangeRateRequired') }}
        </p>
      </div>

      <div>
        <p class="mb-1.5 text-sm font-medium text-highlighted">
          {{ t('app.pos.paperSize') }}
        </p>
        <div class="grid grid-cols-2 gap-2">
          <UButton
            v-for="option in paperOptions"
            :key="option.value"
            :color="option.primary ? 'primary' : 'neutral'"
            :variant="option.primary ? 'subtle' : 'outline'"
            size="xl"
            :icon="option.icon"
            :label="t(option.labelKey)"
            :disabled="!rateValid"
            class="justify-center"
            @click="choose(option.value)"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex w-full justify-end">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="open = false"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
