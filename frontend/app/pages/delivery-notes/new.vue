<script setup lang="ts">
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useSettingsRepositories } from '~/repositories/index'
import type { AppRecord } from '~/config/admin-seed'

/**
 * Create a delivery note (spec §2.1.9 / §5.13). Thin page shell over the
 * reusable `DeliveryNoteCreateFlow` component — purchase-style document:
 * "Delivery Information" header + a line table where each row adds one
 * invoice line (invoice → product → qty). Two entry points reuse the same
 * component: manual create here, and POS post-sale auto-entry via
 * `?saleId=&phone=&location=` (lines prefilled + destination prefilled).
 */
definePageMeta({
  titleKey: 'app.pages.deliveryNotes',
  permission: 'delivery.create',
})

const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()
const { appInfo } = useSettingsRepositories()

onBeforeUnmount(clear)

const shopName = ref('Yoeun Sokhon Pharmacy')

setTitle(t('app.delivery.newTitle'))
setBreadcrumbs([
  { label: t('app.nav.deliveryNotes'), to: '/delivery-notes' },
  { label: t('app.delivery.newTitle') },
])

onMounted(async () => {
  try {
    const info = await appInfo.get()
    const name = String(info.businessName || info.applicationName || '').trim()
    if (name) shopName.value = name
  }
  catch {
    // Keep default shop name when settings are unavailable.
  }
})

const autoSelectSaleId = computed(() => String(route.query.saleId || ''))
const initialPhone = computed(() => String(route.query.phone || '').trim())
const initialLocation = computed(() => String(route.query.location || '').trim())

function onCreated(record: AppRecord) {
  void navigateTo(`/delivery-notes/${String(record.id)}`)
}
</script>

<template>
  <DeliveryNoteCreateFlow
    :key="autoSelectSaleId"
    :auto-select-sale-id="autoSelectSaleId"
    :initial-phone="initialPhone"
    :initial-location="initialLocation"
    :can-confirm="auth.canAccessPage('delivery.confirm')"
    :shop-name="shopName"
    :print-on-create="true"
    @created="onCreated"
  />
</template>