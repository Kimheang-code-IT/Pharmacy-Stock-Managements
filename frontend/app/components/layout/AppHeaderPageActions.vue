<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { ExportFieldOption, ExportRequest } from '~/types/stock-pos/export'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { headerListNavDisabled } from '~/utils/layout/header-actions'

/**
 * Registers reusable header actions with layout AppHeader.
 * Catalog: list nav → slotted extras → refresh → ⋯ (export) → save/cancel → create.
 * Create is opt-in: pass :can-create="true" only on pages that open a /new flow.
 * Use createButtons for multiple create actions (e.g. Add Topic + Add Meeting).
 * Keep #leading / default slots only for rare extras (settings test buttons, job workflow).
 */
const props = withDefaults(defineProps<{
  canCreate?: boolean
  canExport?: boolean
  createLabel?: string
  createIcon?: string
  createButtons?: Array<{ label: string, icon?: string }>
  refreshing?: boolean
  showRefresh?: boolean
  showMoreActions?: boolean
  allowPrintInMore?: boolean
  moreItems?: DropdownMenuItem[][]
  exportFields?: ExportFieldOption[]
  selectedCount?: number
  exporting?: boolean
  showListNav?: boolean
  listTo?: string
  canNavigatePrevious?: boolean
  canNavigateNext?: boolean
  loadingListNavigation?: boolean
  listNavigationDirection?: 'previous' | 'next' | null
  isCreate?: boolean
  showSave?: boolean
  saveLabel?: string
  saving?: boolean
  showCancel?: boolean
  cancelTo?: string
  showMetaRailToggle?: boolean
  metaRailOpen?: boolean
}>(), {
  canCreate: false,
  canExport: true,
  createLabel: '',
  createIcon: 'i-lucide-plus',
  createButtons: () => [],
  refreshing: false,
  showRefresh: true,
  showMoreActions: true,
  allowPrintInMore: false,
  moreItems: () => [],
  exportFields: () => [],
  selectedCount: 0,
  exporting: false,
  showListNav: false,
  listTo: '',
  canNavigatePrevious: false,
  canNavigateNext: false,
  loadingListNavigation: false,
  listNavigationDirection: null,
  isCreate: false,
  showSave: false,
  saveLabel: '',
  saving: false,
  showCancel: false,
  cancelTo: '',
  showMetaRailToggle: false,
  metaRailOpen: false,
})

const emit = defineEmits<{
  refresh: []
  create: []
  createButton: [index: number]
  export: [request: ExportRequest]
  navigatePrevious: []
  navigateNext: []
  save: []
  cancel: []
  toggleMetaRail: []
}>()

const { t } = useI18n()
const toast = useToast()
const { setActions, clearActions } = useAppHeader()
const slots = useSlots()
const ownerId = ref(0)
const exportOpen = ref(false)
/** Keep-alive pages stay mounted; only the active one may teleport into the header. */
const headerTeleportActive = ref(true)

const resolvedCreateLabel = computed(() =>
  props.createLabel || t('core.actions.addItem'),
)

const resolvedSaveLabel = computed(() =>
  props.saveLabel || (props.isCreate ? t('core.confirm.submit') : t('core.common.save')),
)

const defaultMoreItems = computed<DropdownMenuItem[][]>(() => [[
  {
    label: t('actions.export'),
    icon: 'i-lucide-download',
    onSelect: () => { exportOpen.value = true },
  },
]])

function withoutPrint(items: DropdownMenuItem[][]): DropdownMenuItem[][] {
  const printLabels = new Set([
    'print',
    t('core.document.print').trim().toLowerCase(),
    t('core.rolePermissions.actions.print').trim().toLowerCase(),
  ])
  return items
    .map(group => group.filter((item) => {
      const icon = typeof item === 'object' && item && 'icon' in item ? String(item.icon || '') : ''
      const label = typeof item === 'object' && item && 'label' in item ? String(item.label || '') : ''
      return !icon.includes('printer') && !printLabels.has(label.trim().toLowerCase())
    }))
    .filter(group => group.length > 0)
}

const menuItems = computed(() => {
  if (!props.showMoreActions) return []
  const custom = props.moreItems || []
  const exportItem = props.canExport ? (defaultMoreItems.value[0] || []) : []
  const groups = [
    [...exportItem, ...(custom[0] || [])],
    ...custom.slice(1),
  ]
  return props.allowPrintInMore ? groups.filter(group => group.length > 0) : withoutPrint(groups)
})

function submitExport(request: ExportRequest) {
  emit('export', request)
  if (!props.exporting) {
    exportOpen.value = false
    toast.add({ title: t('core.exportDialog.requestReady'), color: 'success' })
  }
}

function syncActions() {
  const createButtons = props.createButtons?.length
    ? props.createButtons.map((button, index) => ({
        label: button.label,
        icon: button.icon || 'i-lucide-plus',
        onClick: () => emit('createButton', index),
      }))
    : undefined

  ownerId.value = setActions({
    canCreate: props.canCreate === true || Boolean(createButtons?.length),
    createLabel: resolvedCreateLabel.value,
    createIcon: props.createIcon || 'i-lucide-plus',
    createButtons,
    refreshing: Boolean(props.refreshing),
    showRefresh: props.showRefresh,
    moreItems: menuItems.value,
    listNav: props.showListNav
      ? {
          listTo: props.listTo || undefined,
          listLabel: t('core.document.listView'),
          previousLabel: t('core.document.previous'),
          nextLabel: t('core.document.next'),
          previousDisabled: headerListNavDisabled({
            isCreate: props.isCreate,
            canNavigate: props.canNavigatePrevious,
            loading: props.loadingListNavigation,
            direction: props.listNavigationDirection,
          }),
          nextDisabled: headerListNavDisabled({
            isCreate: props.isCreate,
            canNavigate: props.canNavigateNext,
            loading: props.loadingListNavigation,
            direction: props.listNavigationDirection,
          }),
          previousLoading: props.listNavigationDirection === 'previous',
          nextLoading: props.listNavigationDirection === 'next',
          onPrevious: () => emit('navigatePrevious'),
          onNext: () => emit('navigateNext'),
        }
      : undefined,
    save: props.showSave
      ? {
          label: resolvedSaveLabel.value,
          loading: Boolean(props.saving),
          onClick: () => emit('save'),
        }
      : undefined,
    cancel: props.showCancel
      ? {
          label: t('actions.cancel'),
          to: props.cancelTo || undefined,
          onClick: () => emit('cancel'),
        }
      : undefined,
    metaRail: props.showMetaRailToggle
      ? {
          open: Boolean(props.metaRailOpen),
          label: t('core.tabs.details'),
          onToggle: () => emit('toggleMetaRail'),
        }
      : undefined,
    onCreate: () => emit('create'),
    onRefresh: () => emit('refresh'),
  })
}

watch(
  () => [
    props.canCreate,
    resolvedCreateLabel.value,
    props.createIcon,
    props.createButtons,
    props.refreshing,
    props.showRefresh,
    props.showMoreActions,
    menuItems.value,
    props.showListNav,
    props.listTo,
    props.canNavigatePrevious,
    props.canNavigateNext,
    props.loadingListNavigation,
    props.listNavigationDirection,
    props.isCreate,
    props.showSave,
    resolvedSaveLabel.value,
    props.saving,
    props.showCancel,
    props.cancelTo,
    props.showMetaRailToggle,
    props.metaRailOpen,
  ] as const,
  () => syncActions(),
  { immediate: true, deep: true },
)

// Re-register after keep-alive / back-navigation races with the previous page’s clear.
onActivated(() => {
  headerTeleportActive.value = true
  syncActions()
})

onDeactivated(() => {
  headerTeleportActive.value = false
  clearActions(ownerId.value)
})

onBeforeUnmount(() => {
  headerTeleportActive.value = false
  clearActions(ownerId.value)
})
</script>

<template>
  <Teleport v-if="headerTeleportActive && slots.leading" defer to="#app-header-leading">
    <div class="contents">
      <slot name="leading" />
    </div>
  </Teleport>

  <Teleport v-if="headerTeleportActive && slots.default" defer to="#app-header-trailing">
    <div class="contents">
      <slot />
    </div>
  </Teleport>

  <CommonAppExportDialog
    v-model:open="exportOpen"
    :fields="props.exportFields"
    :selected-count="props.selectedCount"
    :loading="props.exporting"
    @submit="submitExport"
  />
</template>
