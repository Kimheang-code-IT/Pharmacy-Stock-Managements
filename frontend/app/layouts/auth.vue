<template>
  <div class="relative h-screen bg-linear-to-br from-primary/20 via-white to-primary/10 dark:from-gray-900 dark:via-gray-950 dark:to-primary/20">
    <div class="absolute inset-e-4 top-4 z-20 sm:inset-e-6 sm:top-6">
      <CommonAppAuthLocaleSwitch />
    </div>

    <div class="flex h-full items-center justify-center px-4">
      <UPageCard variant="subtle" class="w-full max-w-sm">
        <NuxtPage />
      </UPageCard>
    </div>
  </div>
</template>
