<script setup lang="ts">
import { nextTick } from 'vue'
import type { PrintPaperSize } from '~/utils/print/html'
import { printSaleInvoice, saleReceiptPrintInput, type SaleInvoicePrintInput } from '~/utils/print/invoice'
import { usePosCommands, useSettingsRepositories } from '~/repositories/index'
import { apiErrorMessage, isApiErrorHandled, isRequestAborted } from '~/utils/api/errors'

/**
 * "Print Invoice" chooser: opens from any sales list / history, loads the stored
 * receipt and lets the user pick A4 or A5 before printing. The invoice prints in
 * the sale's own currency/exchange-rate snapshot, so a reprint always matches
 * what was sold.
 */
const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(defineProps<{
  /** Sale id whose stored receipt is reprinted. */
  saleId?: string
  /** Override the shop name; otherwise resolved from System Settings. */
  shopName?: string
}>(), {
  saleId: '',
  shopName: '',
})

const { t } = useI18n()
const toast = useToast()
const posCommands = usePosCommands()
const { appInfo } = useSettingsRepositories()

const loading = ref(false)
const printing = ref(false)
const loadError = ref<string | null>(null)
const printInput = ref<SaleInvoicePrintInput | null>(null)
const invoiceNo = ref('')
let cachedShopName = ''

/** Macrotask gap so the closed modal paints before print() blocks the UI. */
const CLOSE_PAINT_MS = 150

async function waitForClosePaint() {
  await nextTick()
  if (typeof requestAnimationFrame === 'function') {
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    })
  }
  await new Promise<void>((resolve) => {
    setTimeout(resolve, CLOSE_PAINT_MS)
  })
}

async function resolveShopName(): Promise<string> {
  if (props.shopName) return props.shopName
  if (cachedShopName) return cachedShopName
  try {
    const info = await appInfo.get()
    cachedShopName = String(info.businessName || info.applicationName || '').trim()
  }
  catch {
    // Keep the default below when System Settings are unavailable.
  }
  return cachedShopName || t('core.brand.name')
}

async function loadReceipt() {
  loadError.value = null
  printInput.value = null
  invoiceNo.value = ''
  if (!props.saleId) return
  loading.value = true
  try {
    const [receipt, shopName] = await Promise.all([
      posCommands.getSaleReceipt(props.saleId),
      resolveShopName(),
    ])
    printInput.value = saleReceiptPrintInput(receipt, shopName)
    invoiceNo.value = receipt.invoiceNo || receipt.saleNo
  }
  catch (error: unknown) {
    // A request cancelled by a newer load (cancelPrevious) is not a failure;
    // only surface real errors. The latest request owns the shown invoice.
    if (!isApiErrorHandled(error) && !isRequestAborted(error)) {
      loadError.value = apiErrorMessage(error, t('app.reports.printFailed'))
    }
  }
  finally {
    loading.value = false
  }
}

// ONE loader for open + saleId. The print action sets both in the same tick, so
// two separate watchers used to fire two identical receipt requests; the first
// was cancelled and surfaced as a bogus "Could not print the invoice" while the
// second succeeded (leaving the invoice number and the error visible together).
watch([open, () => props.saleId], ([isOpen]) => {
  if (isOpen) {
    void loadReceipt()
    return
  }
  printing.value = false
  loadError.value = null
  printInput.value = null
})

async function confirm(size: PrintPaperSize) {
  const input = printInput.value
  if (!input || printing.value) return
  printing.value = true
  // Close first, then let the modal finish its leave transition before the
  // (blocking) print call — otherwise the chooser freezes on screen.
  open.value = false
  try {
    await waitForClosePaint()
    await printSaleInvoice(input, size)
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.reports.printFailed'),
        description: apiErrorMessage(error, t('app.reports.printFailed')),
        color: 'error',
      })
    }
  }
  finally {
    printing.value = false
  }
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.reports.printInvoice')"
    icon="i-lucide-printer"
    size="sm"
    :loading="loading"
    :prevent-close-on-loading="false"
  >
    <div class="w-full space-y-3">
      <p v-if="invoiceNo" class="text-sm text-muted">
        {{ t('app.fields.invoiceNo') }}: <span class="font-medium text-highlighted">{{ invoiceNo }}</span>
      </p>

      <div v-if="loading" class="flex items-center justify-center gap-2 py-4 text-sm text-muted">
        <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
        {{ t('app.reports.printLoading') }}
      </div>

      <p v-else-if="loadError" class="text-sm text-error">{{ loadError }}</p>

      <template v-else-if="printInput">
        <p class="text-sm text-muted">{{ t('app.pos.paperSize') }}</p>
        <div class="grid grid-cols-2 gap-2">
          <UButton
            block
            size="lg"
            color="primary"
            icon="i-lucide-file-text"
            :label="t('app.pos.paperA4')"
            @click="confirm('A4')"
          />
          <UButton
            block
            size="lg"
            color="neutral"
            variant="soft"
            icon="i-lucide-file"
            :label="t('app.pos.paperA5')"
            @click="confirm('A5')"
          />
        </div>
      </template>

      <p v-else class="text-sm text-error">{{ t('app.reports.printFailed') }}</p>
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
