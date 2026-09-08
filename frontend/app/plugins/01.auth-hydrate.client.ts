export default defineNuxtPlugin(() => {
  // Restore the locally persisted display profile before route middleware runs.
  // API revalidation is started from app.vue, where component-only composables
  // such as useI18n() are valid.
  const auth = useAuthStore()
  auth.hydrateClient()
})
