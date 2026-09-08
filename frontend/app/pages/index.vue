<script setup lang="ts">
definePageMeta({
  titleKey: 'app.pages.dashboard',
  permission: 'dashboard.view',
})
</script>

<template>
  <div class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
    <DashboardStockDashboardView />
  </div>
</template>