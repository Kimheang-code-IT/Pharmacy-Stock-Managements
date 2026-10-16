<script setup lang="ts">
import { nextTick } from 'vue'
import type { PrintPaperSize } from '~/utils/print/html'
import { printPaymentReceipt, type PaymentReceiptInput } from '~/utils/print/payment-receipt'
import { useSettingsRepositories } from '~/repositories/index'
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'

/**
 * A4/A5 chooser for a debt payment receipt. The payload is assembled by the
 * caller right after the payment is saved (no backend fetch), so the chooser
 * opens instantly and prints the party a document for the money received.
 */
const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(defineProps<{
  /** Payment receipt assembled after a debt payment (null = nothing to print). */
  receipt?: PaymentReceiptInput | null
  /** Override the shop name; otherwise resolved from System Settings. */
  shopName?: string
}>(), {
  receipt: null,
  shopName: '',
})

const { t } = useI18n()
const toast = useToast()
const { appInfo } = useSettingsRepositories()

const printing = ref(false)
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

async function confirm(size: PrintPaperSize) {
  const receipt = props.receipt
  if (!receipt || printing.value) return
  printing.value = true
  // Close first, then let the modal finish its leave transition before the
  // (blocking) print call — otherwise the chooser freezes on screen.
  open.value = false
  try {
    await waitForClosePaint()
    await printPaymentReceipt({ ...receipt, shopName: await resolveShopName() }, size)
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
    :title="t('app.reports.printPaymentReceipt')"
    icon="i-lucide-receipt"
    size="sm"
  >
    <div class="w-full space-y-3">
      <p class="text-sm text-muted">
        {{ t('app.reports.receiptNo') }}:
        <span class="font-medium text-highlighted">{{ receipt?.receiptNo || '—' }}</span>
      </p>

      <template v-if="receipt">
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
