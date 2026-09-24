<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import type { PosCartLine } from '~/utils/pos/cart'
import { cartSubtotal, lineDiscountAmount, lineGross, lineNet } from '~/utils/pos/cart'

const props = withDefaults(defineProps<{
  cart: PosCartLine[]
  disabled?: boolean
  /** ONE sale currency for the whole cart (USD | KHR) — header selector. */
  saleCurrency?: 'USD' | 'KHR'
  /** Return mode: the original price/UOM/discount are preserved (read-only);
   *  only the return quantity is editable. */
  returnMode?: boolean
  /** Line discounts require `pos.discount`; the backend re-checks on save. */
  canDiscount?: boolean
}>(), {
  disabled: false,
  saleCurrency: 'USD',
  returnMode: false,
  canDiscount: true,
})

const emit = defineEmits<{
  changeQty: [productId: string, delta: number]
  changeUom: [productId: string, uomId: string]
  updatePrice: [productId: string, unitPrice: number]
  updateDiscount: [productId: string, discountPercent: number]
  updateSaleCurrency: [value: 'USD' | 'KHR']
  remove: [productId: string]
  clear: []
  back: []
  next: []
}>()

const { t } = useI18n()

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

/** Cart amounts are stored in the sale currency — no conversion here. */
const money = (value: unknown) => formatMoney(Number(value || 0), props.saleCurrency)
const subtotal = computed(() => cartSubtotal(props.cart))

function onPriceInput(line: PosCartLine, value: unknown) {
  const amount = Number(value ?? 0)
  emit('updatePrice', line.productId, Number.isFinite(amount) ? Math.max(0, amount) : 0)
}

/** The discount field edits an amount; convert it to the stored percent. */
function onDiscountInput(line: PosCartLine, value: unknown) {
  const amount = Math.max(0, Number(value) || 0)
  const gross = lineGross(line)
  const percent = gross > 0 ? Math.min(100, (amount / gross) * 100) : 0
  emit('updateDiscount', line.productId, percent)
}

/** UOM selection dialog (opened from a row's settings icon). */
const uomDialogOpen = ref(false)
const uomLine = ref<PosCartLine | null>(null)

function openUomDialog(line: PosCartLine) {
  if (props.disabled || props.returnMode) return
  uomLine.value = line
  uomDialogOpen.value = true
}

function selectUom(uomId: string) {
  if (uomLine.value) emit('changeUom', uomLine.value.productId, uomId)
  uomDialogOpen.value = false
}
</script>

<template>
  <section class="flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-default lg:w-[55%] lg:flex-none lg:border-l lg:border-default">
    <div class="flex items-center justify-between border-b border-default px-3 py-2.5">
      <div class="flex items-center gap-2">
        <h2 class="text-sm font-semibold">
          {{ t('app.pos.cart') }}
          <span
            v-if="cart.length"
            class="ml-1 text-muted"
          >({{ cart.length }})</span>
        </h2>
        <!-- Global sale-currency selector: drives every cart amount. -->
        <UFieldGroup>
          <UButton
            v-for="option in currencyOptions"
            :key="option.value"
            size="xs"
            :label="option.symbol"
            :color="saleCurrency === option.value ? 'primary' : 'neutral'"
            :variant="saleCurrency === option.value ? 'soft' : 'outline'"
            :disabled="disabled || returnMode"
            :title="t(option.labelKey)"
            :aria-label="t(option.labelKey)"
            :aria-pressed="saleCurrency === option.value"
            @click="emit('updateSaleCurrency', option.value)"
          />
        </UFieldGroup>
      </div>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        :disabled="!cart.length || disabled"
        :label="t('app.pos.clearCart')"
        @click="emit('clear')"
      />
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <!-- Column headers: UOM · image · product · unit price · qty · discount · amount · remove. -->
      <div class="flex items-center gap-x-2 border-b border-default bg-elevated/40 px-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
        <span class="w-7 shrink-0" />
        <span class="size-9 shrink-0" />
        <span class="min-w-0 flex-1">{{ t('app.pos.product') }}</span>
        <span class="w-32 shrink-0 text-right">{{ t('app.pos.unitPrice') }}</span>
        <span class="w-28 shrink-0 text-center">{{ t('app.pos.qty') }}</span>
        <span
          v-if="canDiscount"
          class="w-28 shrink-0 text-right"
        >{{ t('app.pos.discount') }}</span>
        <span class="w-28 shrink-0 text-right">{{ t('app.pos.amount') }}</span>
        <span class="w-7 shrink-0" />
      </div>

      <!-- One row per line: UOM · image · name · unit price · qty · discount · total · remove. -->
      <div
        v-for="line in cart"
        :key="line.productId"
        class="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-default px-2 py-2"
      >
        <!-- UOM selection (settings icon) — left of the product image. -->
        <UButton
          size="sm"
          color="neutral"
          variant="ghost"
          icon="i-lucide-settings-2"
          square
          class="w-7 shrink-0"
          :disabled="disabled || returnMode"
          :aria-label="t('app.pos.selectUom')"
          @click="openUomDialog(line)"
        />

        <div class="size-9 shrink-0 overflow-hidden rounded-sm bg-elevated">
          <img
            v-if="line.imageUrl"
            :src="line.imageUrl"
            :alt="line.name"
            class="h-full w-full object-cover"
          >
          <div
            v-else
            class="flex h-full w-full items-center justify-center text-muted"
          >
            <UIcon
              name="i-lucide-package"
              class="size-4 opacity-40"
            />
          </div>
        </div>

        <p class="min-w-0 flex-1 truncate text-sm font-medium">
          {{ line.name }}
        </p>

        <!-- Unit price: inline direct edit. -->
        <CommonAppMoneyField
          inline
          :model-value="line.unitPrice"
          :currency="saleCurrency"
          :min="0"
          :step="0.01"
          size="md"
          align="right"
          class="w-32 shrink-0"
          :disabled="disabled || returnMode"
          @update:model-value="onPriceInput(line, $event)"
        />

        <!-- Quantity stepper. -->
        <div class="flex w-28 shrink-0 items-center justify-center">
          <UButton
            size="sm"
            color="primary"
            variant="solid"
            icon="i-lucide-minus"
            square
            :disabled="disabled || line.quantity <= 1"
            @click="emit('changeQty', line.productId, -1)"
          />
          <span class="min-w-7 text-center text-sm font-medium tabular-nums">{{ line.quantity }}</span>
          <UButton
            size="sm"
            color="primary"
            variant="solid"
            icon="i-lucide-plus"
            square
            :disabled="disabled || line.quantity >= line.availableStock"
            @click="emit('changeQty', line.productId, 1)"
          />
        </div>

        <!-- Discount: inline money amount (stored as a percent). -->
        <CommonAppMoneyField
          v-if="canDiscount"
          inline
          :model-value="lineDiscountAmount(line)"
          :currency="saleCurrency"
          :min="0"
          :step="0.01"
          size="md"
          align="right"
          class="w-28 shrink-0"
          :disabled="disabled || returnMode"
          @update:model-value="onDiscountInput(line, $event)"
        />

        <span class="w-28 shrink-0 text-right text-sm font-semibold tabular-nums">
          {{ money(lineNet(line)) }}
        </span>

        <!-- Remove line (end of row, red). -->
        <UButton
          size="sm"
          color="error"
          variant="ghost"
          icon="i-lucide-trash-2"
          square
          class="w-7 shrink-0"
          :disabled="disabled"
          :aria-label="t('app.pos.removeItem')"
          @click="emit('remove', line.productId)"
        />
      </div>

      <p
        v-if="!cart.length"
        class="p-4 text-sm text-muted"
      >
        {{ t('app.pos.emptyCart') }}
      </p>
    </div>

    <!-- Subtotal + Back / Next. -->
    <div class="border-t border-default px-3 py-2.5">
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold uppercase">{{ t('app.pos.subtotal') }}</span>
        <span class="text-lg font-bold tabular-nums">{{ money(subtotal) }}</span>
      </div>
      <div class="mt-2 flex gap-2">
        <UButton
          class="h-12 flex-1 justify-center"
          color="neutral"
          variant="soft"
          icon="i-lucide-arrow-left"
          :label="t('common.back')"
          @click="emit('back')"
        />
        <UButton
          class="h-12 flex-1 justify-center"
          color="primary"
          icon="i-lucide-arrow-right"
          trailing
          :disabled="!cart.length || disabled"
          :label="t('app.pos.next')"
          @click="emit('next')"
        />
      </div>
    </div>

    <!-- UOM selection dialog (opened from a row's settings icon). -->
    <CommonAppDialog
      v-model:open="uomDialogOpen"
      :title="t('app.pos.selectUom')"
      icon="i-lucide-settings-2"
      size="sm"
    >
      <div class="grid gap-2">
        <div class="flex items-center gap-2">
          <div class="size-9 shrink-0 overflow-hidden rounded-sm bg-elevated">
            <img
              v-if="uomLine?.imageUrl"
              :src="uomLine.imageUrl"
              :alt="uomLine.name"
              class="h-full w-full object-cover"
            >
            <div
              v-else
              class="flex h-full w-full items-center justify-center text-muted"
            >
              <UIcon
                name="i-lucide-package"
                class="size-4 opacity-40"
              />
            </div>
          </div>
          <p class="min-w-0 flex-1 truncate text-sm font-medium">
            {{ uomLine?.name }}
          </p>
        </div>
        <UButton
          v-for="option in uomLine?.uomOptions || []"
          :key="option.value"
          block
          class="justify-between"
          :color="option.value === uomLine?.uomId ? 'primary' : 'neutral'"
          :variant="option.value === uomLine?.uomId ? 'solid' : 'soft'"
          :label="option.label"
          @click="selectUom(option.value)"
        />
      </div>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            :label="t('common.cancel')"
            @click="uomDialogOpen = false"
          />
        </div>
      </template>
    </CommonAppDialog>
  </section>
</template>
