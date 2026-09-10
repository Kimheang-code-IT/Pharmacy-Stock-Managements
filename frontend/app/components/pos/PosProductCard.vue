<script setup lang="ts">
import { formatMoney } from '~/composables/module/useModule'
import { productImageUrl } from '~/utils/pos/cart'

const props = defineProps<{
  product: Record<string, unknown>
  currency: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  add: [product: Record<string, unknown>]
}>()

const { t } = useI18n()

const image = computed(() => productImageUrl(props.product))
const stock = computed(() => Number(props.product.quantity || 0))
const outOfStock = computed(() => stock.value <= 0)
const lowStock = computed(() => stock.value > 0 && stock.value <= 10)

const money = (value: unknown) => formatMoney(value, props.currency)
</script>

<template>
  <article
    class="group flex flex-col overflow-hidden rounded-sm border border-default bg-default shadow-sm transition hover:shadow-md"
    :class="outOfStock || disabled ? 'opacity-60' : 'cursor-pointer'"
    @click="!outOfStock && !disabled && emit('add', product)"
  >
    <div class="relative aspect-[4/3] overflow-hidden bg-elevated">
      <img
        v-if="image"
        :src="image"
        :alt="String(product.name || '')"
        class="h-full w-full object-cover transition duration-200 group-hover:scale-[1.03]"
        loading="lazy"
      >
      <div
        v-else
        class="flex h-full w-full items-center justify-center text-muted"
      >
        <UIcon
name="i-lucide-package"
class="size-6 opacity-40" />
      </div>
      <span
        class="absolute left-1 top-1 rounded-sm px-1 py-0.5 text-[9px] font-medium tabular-nums"
        :class="outOfStock
          ? 'bg-error/90 text-white'
          : lowStock
            ? 'bg-warning text-white'
            : 'bg-default/90 text-toned shadow-sm'"
      >
        {{ t('app.pos.stock') }}: {{ stock }}
      </span>
    </div>

    <div class="flex flex-1 items-end gap-1 p-1">
      <div class="min-w-0 flex-1">
        <p class="line-clamp-1 text-[11px] font-semibold leading-snug text-highlighted">
          {{ product.name }}
        </p>
        <p class="text-[11px] font-bold text-primary tabular-nums">
          {{ money(product.salePrice) }}
        </p>
      </div>
      <UButton
        size="xs"
        color="primary"
        variant="solid"
        icon="i-lucide-plus"
        square
        class="shrink-0 p-1"
        :disabled="outOfStock || disabled"
        :aria-label="t('app.pos.addToCart')"
        @click.stop="emit('add', product)"
      />
    </div>
  </article>
</template>
