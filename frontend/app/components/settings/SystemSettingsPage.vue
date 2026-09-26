<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { AppConfig, BackupConfig, BackupJob } from '~/types/stock-pos/settings'
import type { MaintenanceAction } from '~/repositories/contracts/settings'
import { systemSettingsTabs } from '~/config/settings-schemas'
import { useBackupRepository, useSettingsRepositories } from '~/repositories'
import { useConfirm } from '~/composables/common/useConfirm'
import { useAccessAlert } from '~/composables/common/useAccessAlert'
import { useAppPageTitle } from '~/composables/layout/useAppPageTitle'
import { getByPath, setByPath } from '~/utils/object-path'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'

const { appConfig } = useSettingsRepositories()
const backupRepo = useBackupRepository()
const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const canEdit = computed(() => auth.canAccessPage('settings.update'))
const canConfigure = computed(() => auth.canAccessPage('settings.update'))
/** Destructive actions are gated by their own Administrator permissions. */
const canResetData = computed(() => auth.canAccessPage('system.data_reset'))
const canClearTransactions = computed(() => auth.canAccessPage('system.maintenance'))
const canBackup = computed(() => auth.canAccessPage('system.backup'))
const canRestore = computed(() => auth.canAccessPage('system.restore'))
const { showPermissionDenied } = useAccessAlert()
const appLocalization = useAppLocalization()

const pending = ref(true)
const saving = ref(false)
const testingEmail = ref(false)
const testingTelegram = ref(false)
const resettingData = ref(false)
const clearingTransactions = ref(false)
const activeTab = ref('localization')
const model = ref<AppConfig | null>(null)
const backupModel = ref<BackupConfig | null>(null)

/** Backup frequency options (from the loaded config, with sensible defaults). */
const backupFrequencyOptions = computed(() =>
  (backupModel.value?.frequencyOptions?.length ? backupModel.value.frequencyOptions : [1, 3, 6, 12, 24])
    .map(hours => ({ label: t('core.settings.backupFrequencyHours', { hours }), value: String(hours) })),
)

/** Settings tabs with the backup frequency select options resolved at runtime. */
const tabs = computed(() => systemSettingsTabs.map(tab => tab.id !== 'backup'
  ? tab
  : {
      ...tab,
      sections: tab.sections.map(section => ({
        ...section,
        fields: section.fields.map(field => field.key === 'backup.frequencyHours'
          ? { ...field, options: backupFrequencyOptions.value }
          : field),
      })),
    }))

const activeReadOnly = computed(() =>
  activeTab.value === 'backup' ? !canBackup.value : !canEdit.value,
)
const activeCanSave = computed(() =>
  activeTab.value === 'backup' ? canBackup.value : canEdit.value,
)

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

async function loadBackup() {
  try {
    backupModel.value = await backupRepo.getSettings()
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.common.loadFailed')), color: 'error' })
  }
}

async function load() {
  pending.value = true
  try {
    model.value = await appConfig.get()
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.common.loadFailed')), color: 'error' })
  }
  finally {
    pending.value = false
  }
  await loadBackup()
}

function fieldValue(key: string): unknown {
  if (key.startsWith('backup.')) return backupFieldValue(key.slice('backup.'.length))
  if (!model.value) return undefined

  // Select options use string values; coerce number fields for USelect match.
  if (key === 'general.defaultPageSize' || key === 'system.paginationDefault') {
    const raw = getByPath(model.value, key)
    return raw == null || raw === '' ? undefined : String(raw)
  }

  // The notifications tab's language selector maps onto the shared
  // telegram message language (backend `notification_language`).
  if (key === 'telegram.notificationLanguage') {
    const raw = model.value.telegram.messageLanguage
    return raw == null ? undefined : String(raw)
  }

  return getByPath(model.value, key)
}

async function setFieldValue(key: string, value: unknown) {
  if (key.startsWith('backup.')) {
    if (!backupModel.value) return
    const field = key.slice('backup.'.length)
    backupModel.value = field === 'frequencyHours'
      ? { ...backupModel.value, frequencyHours: Number(value) || 24 }
      : { ...backupModel.value, [field]: value } as BackupConfig
    return
  }
  if (!model.value) return

  if (key === 'system.maintenanceMode' || key === 'system.readOnlyMode') {
    if (value === true) {
      const ok = await confirm({
        kind: 'update',
        titleKey: 'core.settings.confirmModeTitle',
        descriptionKey: 'core.settings.confirmModeHelp',
        confirmColor: 'warning',
      })
      if (!ok) return
    }
    setByPath(model.value, key, value)
    return
  }

  if (key === 'general.defaultPageSize' || key === 'system.paginationDefault') {
    const n = Number(value)
    setByPath(model.value, key, Number.isFinite(n) ? n : 20)
    return
  }

  if (key === 'telegram.notificationLanguage') {
    setByPath(model.value, 'telegram.messageLanguage', value === 'km' ? 'km' : 'en')
    return
  }

  setByPath(model.value, key, value)
}

async function save() {
  saving.value = true
  try {
    if (activeTab.value === 'backup') {
      if (!backupModel.value) return
      backupModel.value = await backupRepo.updateSettings(backupModel.value)
      toast.add({ title: t('core.common.saved'), color: 'success' })
      return
    }
    if (!model.value) return
    model.value = await appConfig.update(model.value)
    appLocalization.apply(model.value.localization)
    usePreferencesStore().setCurrency(model.value.localization.currency)
    usePreferencesStore().syncLocaleWithConfig()
    toast.add({ title: t('core.common.saved'), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.common.saveFailed')), color: 'error' })
  }
  finally {
    saving.value = false
  }
}

async function testEmail() {
  testingEmail.value = true
  try {
    if (model.value) await appConfig.update({ email: model.value.email })
    const result = await appConfig.testEmailConnection()
    model.value = await appConfig.get()
    toast.add({
      title: result.message,
      color: result.status === 'connected' ? 'success' : 'error',
    })
  }
  finally {
    testingEmail.value = false
  }
}

async function testTelegram() {
  testingTelegram.value = true
  try {
    if (model.value) await appConfig.update({ telegram: model.value.telegram })
    const result = await appConfig.sendTestTelegramMessage()
    model.value = await appConfig.get()
    toast.add({
      title: result.message,
      color: result.status === 'connected' ? 'success' : 'error',
    })
  }
  finally {
    testingTelegram.value = false
  }
}

/**
 * Guarded destructive flow: the exact confirmation phrase unlocks the action.
 * The backend also requires a verified pre-deletion backup and records
 * protected audit events.
 */
const MAINTENANCE_PHRASES: Record<MaintenanceAction, string> = {
  RESET_ALL_DATA: 'RESET ALL DATA',
  CLEAR_TRANSACTIONS: 'CLEAR TRANSACTIONS',
}
const maintenanceOpen = ref(false)
const maintenanceAction = ref<MaintenanceAction>('CLEAR_TRANSACTIONS')
const maintenancePhrase = ref('')
const maintenanceBusy = ref(false)
const maintenanceTitleKey = computed(() => maintenanceAction.value === 'RESET_ALL_DATA'
  ? 'core.settings.resetDataConfirmTitle'
  : 'core.settings.clearTransactionsConfirmTitle')

function openMaintenance(action: MaintenanceAction) {
  maintenanceAction.value = action
  maintenancePhrase.value = ''
  maintenanceOpen.value = true
}

const canSubmitMaintenance = computed(() => Boolean(maintenancePhrase.value.trim()))

async function submitMaintenance() {
  if (!canSubmitMaintenance.value || maintenanceBusy.value) return
  const action = maintenanceAction.value
  if (maintenancePhrase.value.trim() !== MAINTENANCE_PHRASES[action]) {
    toast.add({ title: t('core.settings.maintenancePhraseMismatch'), color: 'error' })
    return
  }
  maintenanceBusy.value = true
  try {
    const input = {
      confirmationPhrase: maintenancePhrase.value.trim(),
    }
    if (action === 'RESET_ALL_DATA') {
      resettingData.value = true
      await appConfig.resetAllData(input)
      toast.add({ title: t('core.settings.resetDataSuccess'), color: 'success' })
      maintenanceOpen.value = false
      await auth.logout()
    }
    else {
      clearingTransactions.value = true
      await appConfig.clearTransactions(input)
      toast.add({ title: t('core.settings.clearTransactionsSuccess'), color: 'success' })
      maintenanceOpen.value = false
    }
  }
  catch (error: unknown) {
    const key = action === 'RESET_ALL_DATA'
      ? 'core.settings.resetDataFailed'
      : 'core.settings.clearTransactionsFailed'
    toast.add({ title: errorMessage(error, t(key)), color: 'error' })
  }
  finally {
    maintenanceBusy.value = false
    resettingData.value = false
    clearingTransactions.value = false
  }
}

/* ------------------------------ backup actions ------------------------------ */

const backupTesting = ref(false)
const backupRunning = ref(false)
const backupHistoryOpen = ref(false)
const backupHistoryLoading = ref(false)
const backupHistory = ref<BackupJob[]>([])
const backupRestoreOpen = ref(false)
const backupRestorePassword = ref('')
const backupRestorePhrase = ref('')
const backupRestoreBusy = ref(false)
const BACKUP_RESTORE_PHRASE = 'RESTORE DATABASE'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return t('core.settings.backupNever')
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

/** Read a backup field for the standard form (flat keys, formatted status). */
function backupFieldValue(field: string): unknown {
  const backup = backupModel.value
  if (!backup) return undefined
  if (field === 'frequencyHours') return String(backup.frequencyHours)
  if (field === 'lastSuccessAt') return formatDateTime(backup.lastSuccessAt)
  if (field === 'nextRunAt') return formatDateTime(backup.nextRunAt)
  return (backup as unknown as Record<string, unknown>)[field]
}

async function testBackupConnection() {
  backupTesting.value = true
  try {
    if (backupModel.value) await backupRepo.updateSettings(backupModel.value)
    const result = await backupRepo.testConnection()
    toast.add({ title: result.message, color: result.status === 'connected' ? 'success' : 'error' })
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.settings.backupTestFailed')), color: 'error' })
  }
  finally {
    backupTesting.value = false
  }
}

async function runBackup() {
  backupRunning.value = true
  try {
    if (backupModel.value) await backupRepo.updateSettings(backupModel.value)
    const result = await backupRepo.run()
    const job = result.job
    toast.add({
      title: t('core.settings.backupRunDone', { status: job.status }),
      description: t('core.settings.backupRunSummary', {
        appended: job.rowsAppended,
        updated: job.rowsUpdated,
      }),
      color: job.status === 'success' ? 'success' : job.status === 'failed' ? 'error' : 'warning',
    })
    await loadBackup()
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.settings.backupRunFailed')), color: 'error' })
  }
  finally {
    backupRunning.value = false
  }
}

async function openBackupHistory() {
  backupHistoryOpen.value = true
  backupHistoryLoading.value = true
  try {
    const result = await backupRepo.history(1, 20)
    backupHistory.value = result.jobs
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.settings.backupHistoryFailed')), color: 'error' })
  }
  finally {
    backupHistoryLoading.value = false
  }
}

function openBackupRestore() {
  if (!canRestore.value) {
    showPermissionDenied({ permission: 'system.restore' })
    return
  }
  backupRestorePassword.value = ''
  backupRestorePhrase.value = ''
  backupRestoreOpen.value = true
}

const canSubmitBackupRestore = computed(() => Boolean(
  backupRestorePassword.value && backupRestorePhrase.value.trim(),
))

async function submitBackupRestore() {
  if (backupRestorePhrase.value.trim() !== BACKUP_RESTORE_PHRASE || !backupRestorePassword.value) return
  backupRestoreBusy.value = true
  try {
    const confirmation = await backupRepo.requestRestoreConfirmation(backupRestorePassword.value)
    const result = await backupRepo.restore({
      confirmationToken: confirmation.confirmationToken,
      confirmationPhrase: backupRestorePhrase.value.trim(),
    })
    toast.add({ title: t('core.settings.backupRestoreDone', { rows: result.totalRows }), color: 'success' })
    backupRestoreOpen.value = false
    await loadBackup()
  }
  catch (error: unknown) {
    toast.add({ title: errorMessage(error, t('core.settings.backupRestoreFailed')), color: 'error' })
  }
  finally {
    backupRestoreBusy.value = false
  }
}

/**
 * Header ⋯ menu: backup actions (reachable from any settings tab) plus the
 * destructive maintenance actions, all gated by their own permissions.
 */
const headerMenuItems = computed<DropdownMenuItem[][]>(() => {
  const backupItems: DropdownMenuItem[] = []
  if (canBackup.value) {
    backupItems.push({
      label: t('core.settings.backupNow'),
      icon: 'i-lucide-play',
      disabled: backupRunning.value || !backupModel.value?.configured,
      onSelect: () => { void runBackup() },
    })
  }
  backupItems.push({
    label: t('core.settings.backupHistory'),
    icon: 'i-lucide-history',
    onSelect: () => { void openBackupHistory() },
  })
  if (canRestore.value) {
    backupItems.push({
      label: t('core.settings.backupRestore'),
      icon: 'i-lucide-database-backup',
      color: 'error',
      disabled: backupRestoreBusy.value || !backupModel.value?.configured,
      onSelect: () => { openBackupRestore() },
    })
  }

  const dangerItems: DropdownMenuItem[] = []
  if (canResetData.value) {
    dangerItems.push({
      label: t('core.settings.resetDataAction'),
      icon: 'i-lucide-database-zap',
      color: 'error',
      disabled: resettingData.value,
      onSelect: () => { openMaintenance('RESET_ALL_DATA') },
    })
  }
  if (canClearTransactions.value) {
    dangerItems.push({
      label: t('core.settings.clearTransactionsAction'),
      icon: 'i-lucide-trash-2',
      color: 'error',
      disabled: clearingTransactions.value,
      onSelect: () => { openMaintenance('CLEAR_TRANSACTIONS') },
    })
  }

  const groups: DropdownMenuItem[][] = []
  if (backupItems.length) groups.push(backupItems)
  if (dangerItems.length) groups.push(dangerItems)
  return groups
})

onMounted(() => void load())
useAppPageTitle(() => t('app.pages.settings'))
</script>

<template>
  <DocumentAppDocumentPage
    v-model:active-tab="activeTab"
    :tabs="tabs"
    :field-value="fieldValue"
    :set-field-value="setFieldValue"
    :pending="pending || !model"
    :saving="saving"
    :read-only="activeReadOnly"
    :can-save="activeCanSave"
    :show-list-nav="false"
    :more-items="headerMenuItems"
    content-wide
    @save="save"
    @refresh="load"
  >
    <template #actions>
      <CommonAppConnectionTestButton
        v-if="activeTab === 'email' && canConfigure"
        :loading="testingEmail"
        @click="testEmail"
      />
      <CommonAppConnectionTestButton
        v-if="activeTab === 'telegram' && canConfigure"
        :loading="testingTelegram"
        @click="testTelegram"
      />
      <CommonAppConnectionTestButton
        v-if="activeTab === 'backup' && canBackup"
        :loading="backupTesting"
        :disabled="!backupModel?.configured"
        @click="testBackupConnection"
      />
    </template>

    <template #form>
      <DocumentAppDocumentForm
        :tabs="tabs"
        :active-tab="activeTab"
        :field-value="fieldValue"
        :set-field-value="setFieldValue"
        :read-only="activeReadOnly"
        wide
      />
    </template>
  </DocumentAppDocumentPage>

  <CommonAppDialog
    v-model:open="maintenanceOpen"
    :title="t(maintenanceTitleKey)"
    icon="i-lucide-shield-alert"
    size="sm"
    :loading="maintenanceBusy"
  >
    <div class="w-full space-y-3">
      <p class="text-sm text-muted">
        {{ t('core.settings.maintenanceConfirmHelp') }}
      </p>
      <UFormField
        :label="t('core.settings.maintenancePhrase')"
        :help="t('core.settings.maintenancePhraseHint', { phrase: MAINTENANCE_PHRASES[maintenanceAction] })"
        required
      >
        <UInput v-model="maintenancePhrase" size="lg" class="w-full" />
      </UFormField>
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="maintenanceOpen = false"
        />
        <UButton
          color="error"
          icon="i-lucide-shield-alert"
          :loading="maintenanceBusy"
          :disabled="!canSubmitMaintenance"
          :label="t('core.settings.maintenanceConfirmAction')"
          @click="submitMaintenance"
        />
      </div>
    </template>
  </CommonAppDialog>

  <CommonAppDialog
    v-model:open="backupHistoryOpen"
    :title="t('core.settings.backupHistory')"
    icon="i-lucide-history"
    width="3xl"
    :loading="backupHistoryLoading"
  >
    <div v-if="backupHistoryLoading" class="flex justify-center py-6">
      <UIcon name="i-lucide-loader-circle" class="size-5 animate-spin text-primary" />
    </div>
    <div v-else-if="!backupHistory.length" class="py-6 text-center text-sm text-muted">
      {{ t('core.settings.backupHistoryEmpty') }}
    </div>
    <ul v-else class="divide-y divide-default">
      <li v-for="job in backupHistory" :key="job.id" class="flex flex-col gap-1 py-3 text-sm">
        <div class="flex flex-wrap items-center gap-2">
          <UBadge
            :color="job.status === 'success' ? 'success' : job.status === 'failed' ? 'error' : job.status === 'partial' ? 'warning' : 'neutral'"
            variant="soft"
          >
            {{ job.status }}
          </UBadge>
          <span class="text-highlighted">{{ formatDateTime(job.startedAt) }}</span>
          <span class="text-muted">({{ job.trigger }})</span>
          <span class="ms-auto text-muted">
            {{ t('core.settings.backupHistoryCounts', { tables: `${job.tablesSucceeded}/${job.tablesTotal}`, appended: job.rowsAppended, updated: job.rowsUpdated }) }}
          </span>
        </div>
        <p v-if="job.errorMessage" class="text-xs text-error">{{ job.errorMessage }}</p>
      </li>
    </ul>
    <template #footer>
      <div class="flex w-full justify-end">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.close')"
          @click="backupHistoryOpen = false"
        />
      </div>
    </template>
  </CommonAppDialog>

  <CommonAppDialog
    v-model:open="backupRestoreOpen"
    :title="t('core.settings.backupRestore')"
    icon="i-lucide-database-backup"
    color="error"
    size="sm"
    :loading="backupRestoreBusy"
  >
    <div class="w-full space-y-3">
      <p class="text-sm text-muted">{{ t('core.settings.backupRestoreHelp') }}</p>
      <UFormField :label="t('core.settings.maintenancePassword')" required>
        <UInput
          v-model="backupRestorePassword"
          type="password"
          autocomplete="current-password"
          class="w-full"
        />
      </UFormField>
      <UFormField
        :label="t('core.settings.maintenancePhrase')"
        :help="t('core.settings.maintenancePhraseHint', { phrase: BACKUP_RESTORE_PHRASE })"
        required
      >
        <UInput v-model="backupRestorePhrase" class="w-full" />
      </UFormField>
    </div>
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="backupRestoreOpen = false"
        />
        <UButton
          color="error"
          icon="i-lucide-database-backup"
          :loading="backupRestoreBusy"
          :disabled="!canSubmitBackupRestore"
          :label="t('core.settings.backupRestoreConfirm')"
          @click="submitBackupRestore"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
