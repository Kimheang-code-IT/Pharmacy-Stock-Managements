<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import type { PosCartLine } from '~/utils/pos/cart'
import { lineNet } from '~/utils/pos/cart'

const props = withDefaults(defineProps<{
  cart: PosCartLine[]
  currency: string
  disabled?: boolean
  /** Document currency of THIS sale (USD | KHR) — toggled from the price fields. */
  saleCurrency?: 'USD' | 'KHR'
  /** USD → document-currency multiplier (1 for USD sales). */
  saleRate?: number
}>(), {
  disabled: false,
  saleCurrency: 'USD',
  saleRate: 1,
})

const emit = defineEmits<{
  changeQty: [productId: string, delta: number]
  changeUom: [productId: string, uomId: string]
  updatePrice: [productId: string, unitPrice: number]
  updateDiscount: [productId: string, discountPercent: number]
  updateSaleCurrency: [value: 'USD' | 'KHR']
  remove: [productId: string]
  clear: []
}>()

const { t } = useI18n()

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]

/** Display currency: the document currency for KHR sales, else the shop default. */
const displayCurrency = computed(() => props.saleCurrency === 'KHR' ? 'KHR' : props.currency)
const money = (value: unknown) => formatMoney(Number(value || 0) * props.saleRate, displayCurrency.value)

/** KHR unit prices are read/edited at the sale rate (falls back to USD
 *  display until the exchange rate is entered). */
const converting = computed(() => props.saleCurrency === 'KHR' && props.saleRate > 0)

function priceInputValue(line: PosCartLine) {
  return converting.value ? line.unitPrice * props.saleRate : line.unitPrice
}

function onPriceInput(line: PosCartLine, value: unknown) {
  const amount = Number(value ?? 0)
  const unitPrice = converting.value ? amount / props.saleRate : amount
  emit('updatePrice', line.productId, Number.isFinite(unitPrice) ? Math.max(0, unitPrice) : 0)
}

function padQty(qty: number) {
  return String(qty).padStart(2, '0')
}
</script>

<template>
  <section class="flex w-full min-h-0 flex-[3] flex-col overflow-hidden rounded-sm border border-default bg-default lg:max-w-md">
    <div class="flex items-center justify-between border-b border-default px-3 py-2.5">
      <h2 class="text-sm font-semibold">
        {{ t('app.pos.cart') }}
        <span
v-if="cart.length"
class="ml-1 text-muted">({{ cart.length }})</span>
      </h2>
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
      <div
        v-for="line in cart"
        :key="line.productId"
        class="border-b border-default px-3 py-3"
      >
        <div class="flex gap-2.5">
          <div class="size-12 shrink-0 overflow-hidden rounded-sm bg-elevated">
            <img
              v-if="line.imageUrl"
              :src="line.imageUrl"
              :alt="line.name"
              class="h-full w-full object-cover"
            >
            <div
v-else
class="flex h-full w-full items-center justify-center text-muted">
              <UIcon
name="i-lucide-package"
class="size-5 opacity-40" />
            </div>
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex items-start gap-1">
              <p class="min-w-0 flex-1 truncate text-sm font-medium">
                {{ line.name }}
              </p>
              <UButton
                size="xs"
                color="neutral"
                variant="ghost"
                icon="i-lucide-trash-2"
                class="shrink-0"
                :disabled="disabled"
                :aria-label="t('app.pos.removeItem')"
                @click="emit('remove', line.productId)"
              />
            </div>

            <div class="mt-2 flex items-center gap-2">
              <div class="flex items-center gap-1">
                <UButton
                  size="xs"
                  color="neutral"
                  variant="soft"
                  icon="i-lucide-minus"
                  square
                  :disabled="disabled || line.quantity <= 1"
                  @click="emit('changeQty', line.productId, -1)"
                />
                <span class="min-w-8 text-center text-sm font-medium tabular-nums">
                  {{ padQty(line.quantity) }}
                </span>
                <UButton
                  size="xs"
                  color="neutral"
                  variant="soft"
                  icon="i-lucide-plus"
                  square
                  :disabled="disabled || line.quantity >= line.availableStock"
                  @click="emit('changeQty', line.productId, 1)"
                />
              </div>
              <USelect
                v-if="line.uomOptions.length > 1"
                :model-value="line.uomId"
                :items="line.uomOptions"
                size="xs"
                class="w-24"
                :disabled="disabled"
                :aria-label="t('app.pos.uom')"
                @update:model-value="emit('changeUom', line.productId, String($event))"
              />
              <span v-else class="ml-auto text-xs text-muted">{{ line.uom }}</span>
              <span class="ml-auto text-sm font-semibold tabular-nums">
                {{ money(lineNet(line)) }}
              </span>
            </div>

            <div class="mt-2 grid grid-cols-2 gap-2">
              <UFormField
                :label="t('app.pos.unitPrice')"
                size="xs"
              >
                <UFieldGroup class="w-full">
                  <UInputNumber
                    :model-value="priceInputValue(line)"
                    :min="0"
                    :step="0.01"
                    :increment="false"
                    :decrement="false"
                    size="md"
                    class="w-full"
                    :ui="{ base: 'text-base tabular-nums' }"
                    :disabled="disabled"
                    @update:model-value="onPriceInput(line, $event)"
                  />
                  <UButton
                    v-for="option in currencyOptions"
                    :key="option.value"
                    :label="option.symbol"
                    :color="saleCurrency === option.value ? 'primary' : 'neutral'"
                    :variant="saleCurrency === option.value ? 'soft' : 'outline'"
                    :disabled="disabled"
                    :title="t(option.labelKey)"
                    :aria-label="t(option.labelKey)"
                    :aria-pressed="saleCurrency === option.value"
                    @click="emit('updateSaleCurrency', option.value)"
                  />
                </UFieldGroup>
              </UFormField>
              <UFormField
                :label="t('app.pos.lineDiscount')"
                size="xs"
              >
                <div class="relative">
                  <UInputNumber
                    :model-value="line.discountPercent"
                    :min="0"
                    :max="100"
                    :step="1"
                    :increment="false"
                    :decrement="false"
                    size="md"
                    class="w-full"
                    :ui="{ base: 'text-base tabular-nums' }"
                    :disabled="disabled"
                    @update:model-value="emit('updateDiscount', line.productId, Number($event ?? 0))"
                  />
                  <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center text-sm text-muted">%</span>
                </div>
              </UFormField>
            </div>
          </div>
        </div>
      </div>

      <p
v-if="!cart.length"
class="p-4 text-sm text-muted">
        {{ t('app.pos.emptyCart') }}
      </p>
    </div>
  </section>
</template>
