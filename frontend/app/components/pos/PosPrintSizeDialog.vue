<script setup lang="ts">
import type { PrintPaperSize } from '~/utils/print/html'

/**
 * Paper-size chooser shown right after a successful POS Submit (spec: no
 * invoice preview dialog — sale completes, cashier picks A4 or A5, the
 * bilingual invoice prints through the hidden-iframe print document).
 * Closing/cancel skips printing; the sale is already saved.
 */
const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  confirm: [size: PrintPaperSize]
}>()

const { t } = useI18n()

/** Two options only; A4 is the default choice (listed/emphasized first). */
const paperOptions: Array<{ value: PrintPaperSize, icon: string, labelKey: string, primary?: boolean }> = [
  { value: 'A4', icon: 'i-lucide-file-text', labelKey: 'app.pos.paperA4', primary: true },
  { value: 'A5', icon: 'i-lucide-file', labelKey: 'app.pos.paperA5' },
]

function choose(size: PrintPaperSize) {
  open.value = false
  emit('confirm', size)
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.pos.printSizeTitle')"
    icon="i-lucide-printer"
    size="sm"
  >
    <div class="grid grid-cols-2 gap-2">
      <UButton
        v-for="option in paperOptions"
        :key="option.value"
        :color="option.primary ? 'primary' : 'neutral'"
        :variant="option.primary ? 'subtle' : 'outline'"
        size="xl"
        :icon="option.icon"
        :label="t(option.labelKey)"
        class="justify-center"
        @click="choose(option.value)"
      />
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
