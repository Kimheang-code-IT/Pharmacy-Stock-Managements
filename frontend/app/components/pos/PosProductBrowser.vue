<script setup lang="ts">
import PosProductCard from '~/components/pos/PosProductCard.vue'

defineProps<{
  products: Record<string, unknown>[]
  categories: Array<{ label: string, value: string }>
  search: string
  categoryId: string
  currency: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:search': [value: string]
  'update:categoryId': [value: string]
  add: [product: Record<string, unknown>]
  searchEnter: []
}>()

const { t } = useI18n()
</script>

<template>
  <section class="flex min-h-0 min-w-0 flex-[7] flex-col gap-2">
    <div class="flex flex-col gap-2 sm:flex-row">
      <UInput
        :model-value="search"
        icon="i-lucide-scan-barcode"
        size="lg"
        class="min-w-0 flex-1"
        :placeholder="t('app.pos.searchPlaceholder')"
        autofocus
        @update:model-value="emit('update:search', String($event ?? ''))"
        @keydown.enter.prevent="emit('searchEnter')"
      />
    </div>

    <div class="flex gap-1.5 overflow-x-auto pb-0.5">
      <UButton
        v-for="cat in categories"
        :key="cat.value || 'all'"
        size="lg"
        :color="categoryId === cat.value ? 'primary' : 'neutral'"
        :variant="categoryId === cat.value ? 'solid' : 'soft'"
        :label="cat.label"
        class="shrink-0"
        @click="emit('update:categoryId', cat.value)"
      />
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto rounded-sm bg-muted/40 p-2">
      <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
        <PosProductCard
          v-for="row in products"
          :key="String(row.id)"
          :product="row"
          :currency="currency"
          :disabled="disabled"
          @add="emit('add', $event)"
        />
      </div>
      <p
v-if="!products.length"
class="p-6 text-center text-sm text-muted">
        {{ t('app.ui.noRecords') }}
      </p>
    </div>
  </section>
</template>
