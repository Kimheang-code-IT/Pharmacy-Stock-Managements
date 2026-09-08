<script setup lang="ts">
import type { AppRolePermissionRow } from '~/types/stock-pos/entities'
import {
  ROLE_DOCUMENT_TYPES,
  normalizePermissionRows,
  setPermissionAction,
} from '~/utils/role/permissions'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import type { ApiResponse } from '~/types/stock-pos/common'

const rows = defineModel<AppRolePermissionRow[]>({ default: () => [] })

const props = withDefaults(defineProps<{ disabled?: boolean }>(), {
  disabled: false,
})

const { t, te } = useI18n()
const api = useApi()
const definitions = ref<Array<(typeof ROLE_DOCUMENT_TYPES)[number]>>([])

const displayRows = computed(() => normalizePermissionRows(rows.value))
const grantedCount = computed(() => displayRows.value.reduce((sum, row) => sum + row.actions.length, 0))
const totalCount = computed(() => definitions.value.reduce((sum, definition) => sum + definition.actions.length, 0))
const allGranted = computed(() => grantedCount.value === totalCount.value)
const someGranted = computed(() => grantedCount.value > 0 && !allGranted.value)

function commit(next: AppRolePermissionRow[]) {
  rows.value = normalizePermissionRows(next)
}

function ensureAllRows() {
  const next = normalizePermissionRows(rows.value)
  if (JSON.stringify(next) !== JSON.stringify(rows.value)) rows.value = next
}

onMounted(async () => {
  ensureAllRows()
  try {
    const response = await api.get<ApiResponse<Array<{ module: string, actions: string[] }>>>(
      ApiEndpoints.PERMISSIONS,
      { suppressErrorToast: true, requestKey: 'permission-catalog' },
    )
    const catalog = Array.isArray(response) ? response : response.data
    definitions.value = catalog.map((group) => {
      const existing = ROLE_DOCUMENT_TYPES.find(item => item.permissionPrefix === group.module)
      return existing
        ? { ...existing, actions: group.actions.filter((action: string) => existing.actions.includes(action as never)) as typeof existing.actions }
        : null
    }).filter(Boolean) as unknown as typeof definitions.value
  }
  catch {
    // The backend catalog is authoritative when available; fail closed if it
    // cannot be loaded so roles cannot accidentally receive stale permissions.
    definitions.value = []
  }
})
watch(rows, ensureAllRows, { deep: false })

function documentTypeLabel(value: string) {
  const found = definitions.value.find(item => item.value === value)
  if (found && te(found.labelKey)) return t(found.labelKey)
  return value.replaceAll('_', ' ')
}

function actionLabel(action: string) {
  const key = `core.rolePermissions.actions.${action}`
  return te(key) ? t(key) : action
}

function hasAction(row: AppRolePermissionRow, action: string) {
  return row.actions.includes(action)
}

function allowedActions(documentType: string) {
  return definitions.value.find(item => item.value === documentType)?.actions || []
}

function toggleAction(documentType: string, action: string, checked: boolean | 'indeterminate') {
  if (props.disabled) return
  commit(displayRows.value.map(row =>
    row.documentType === documentType
      ? setPermissionAction(row, action, checked === true)
      : row,
  ))
}

function toggleRow(documentType: string, checked: boolean | 'indeterminate') {
  if (props.disabled) return
  commit(displayRows.value.map(row => row.documentType === documentType
    ? {
        ...row,
        actions: checked === true ? [...allowedActions(documentType)] : [],
        onlyIfCreator: false,
      }
    : row))
}

function toggleAll(checked: boolean) {
  if (props.disabled) return
  commit(displayRows.value.map(row => ({
    ...row,
    actions: checked ? [...allowedActions(row.documentType)] : [],
    onlyIfCreator: false,
  })))
}
</script>

<template>
  <div class="overflow-hidden rounded-sm border border-default">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-default bg-elevated/70 px-3 py-2.5">
      <div>
        <p class="text-sm font-semibold text-highlighted">{{ $t('core.rolePermissions.matrixTitle') }}</p>
        <p class="text-xs text-muted">
          {{ $t('core.rolePermissions.grantedCount', { granted: grantedCount, total: totalCount }) }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          color="neutral"
          variant="outline"
          size="sm"
          icon="i-lucide-shield-x"
          :disabled="disabled || grantedCount === 0"
          @click="toggleAll(false)"
        >
          {{ $t('core.rolePermissions.clearAll') }}
        </UButton>
        <UButton
          color="error"
          variant="soft"
          size="sm"
          icon="i-lucide-shield-plus"
          :disabled="disabled || allGranted"
          @click="toggleAll(true)"
        >
          {{ $t('core.rolePermissions.grantAll') }}
        </UButton>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="min-w-xl w-full text-sm">
        <thead>
          <tr class="bg-elevated/50 text-left text-highlighted">
            <th class="w-12 px-3 py-2.5">
              <UCheckbox
                :model-value="allGranted ? true : someGranted ? 'indeterminate' : false"
                :disabled="disabled"
                :aria-label="$t('core.rolePermissions.grantAll')"
                @update:model-value="toggleAll($event === true)"
              />
            </th>
            <th class="w-[28%] whitespace-nowrap px-3 py-2.5 font-semibold">
              {{ $t('core.rolePermissions.documentType') }}
            </th>
            <th class="px-3 py-2.5 font-semibold">{{ $t('core.fields.permissions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.documentType" class="align-top border-t border-default">
            <td class="px-3 py-3">
              <UCheckbox
                :model-value="row.actions.length > 0 && row.actions.length === allowedActions(row.documentType).length"
                :disabled="disabled"
                :aria-label="$t('core.rolePermissions.toggleRow', { entity: documentTypeLabel(row.documentType) })"
                @update:model-value="toggleRow(row.documentType, $event)"
              />
            </td>
            <td class="px-3 py-3 font-medium text-highlighted">
              {{ documentTypeLabel(row.documentType) }}
            </td>
            <td class="px-3 py-3">
              <div class="flex flex-wrap gap-x-4 gap-y-2">
                <label
                  v-for="action in allowedActions(row.documentType)"
                  :key="action"
                  class="flex min-w-24 cursor-pointer items-center gap-1.5 text-sm text-highlighted"
                >
                  <UCheckbox
                    :model-value="hasAction(row, action)"
                    :disabled="disabled"
                    size="sm"
                    @update:model-value="toggleAction(row.documentType, action, $event)"
                  />
                  <span>{{ actionLabel(action) }}</span>
                </label>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="border-t border-default bg-muted/30 px-3 py-2 text-xs text-muted">
      {{ $t('core.rolePermissions.dependencyHint') }}
    </div>
  </div>
</template>
