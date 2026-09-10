<script setup lang="ts">
/**
 * Quick customer creation from the POS checkout "Add new customer" button
 * (spec §5.11). Name is required; phone/location optional. The customer is
 * created through the canonical customers endpoint (POST /api/v1/customers —
 * the same master-data contract as Setup → Customers), appears on the
 * Customers table, and is auto-selected on the checkout.
 */
const props = defineProps<{
  /** Prefill the name typed into the customer selector before opening. */
  prefillName?: string
  disabled?: boolean
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  /** Emits the created customer's id once saved. */
  created: [customerId: string]
}>()

const { t } = useI18n()
const toast = useToast()
const store = useAppDataStore()
const fieldUi = { base: 'text-base' }

const saving = ref(false)
const name = ref('')
const phone = ref('')
const location = ref('')

watch(open, (value) => {
  if (!value) return
  name.value = props.prefillName || ''
  phone.value = ''
  location.value = ''
})

const canSave = computed(() => Boolean(name.value.trim()))

async function submit() {
  const customerName = name.value.trim()
  if (!customerName || saving.value || props.disabled) return
  saving.value = true
  try {
    const record = await store.createRemote('customers', {
      name: customerName,
      phone: phone.value.trim() || null,
      location: location.value.trim() || null,
      status: 'Active',
    })
    toast.add({ title: t('app.pos.customerCreated', { name: customerName }), color: 'success' })
    open.value = false
    emit('created', String(record.id))
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.pos.customerCreateFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.pos.addNewCustomer')"
    icon="i-lucide-user-plus"
    size="sm"
  >
    <div class="grid gap-3">
      <UFormField
        :label="t('app.pos.customerName')"
        size="md"
        required
      >
        <UInput
          v-model="name"
          class="w-full"
          size="lg"
          :ui="fieldUi"
          :placeholder="t('app.pos.customerName')"
          :disabled="disabled || saving"
          @keydown.enter.prevent="submit"
        />
      </UFormField>
      <UFormField
        :label="t('app.pos.customerPhone')"
        size="md"
      >
        <UInput
          v-model="phone"
          class="w-full"
          size="lg"
          :ui="fieldUi"
          placeholder="012 xxx xxx"
          :disabled="disabled || saving"
        />
      </UFormField>
      <UFormField
        :label="t('app.pos.location')"
        size="md"
      >
        <UInput
          v-model="location"
          class="w-full"
          size="lg"
          :ui="fieldUi"
          :placeholder="t('app.pos.locationPlaceholder')"
          :disabled="disabled || saving"
        />
      </UFormField>
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          :disabled="saving"
          @click="open = false"
        />
        <UButton
          color="primary"
          :label="t('app.pos.saveCustomer')"
          :loading="saving"
          :disabled="disabled || !canSave"
          @click="submit"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>