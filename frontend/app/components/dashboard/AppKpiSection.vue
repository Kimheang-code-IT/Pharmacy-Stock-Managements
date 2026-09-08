<script setup lang="ts">
export type DashboardKpiCard = {
  key: string
  title: string
  value: string | number
  to?: string
}

withDefaults(defineProps<{
  cards: DashboardKpiCard[]
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  refresh: []
}>()
</script>

<template>
  <section class="shrink-0">
    <div class="mt-1 grid grid-cols-2 gap-2 lg:grid-cols-4">
      <DashboardAppSummaryCard
v-for="card in cards"
:key="card.key"
:title="card.title"
:value="card.value"
        :to="card.to"
:loading="loading"
@refresh="emit('refresh')" />
    </div>
  </section>
</template>
