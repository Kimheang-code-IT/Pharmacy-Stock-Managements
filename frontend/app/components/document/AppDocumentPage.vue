<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type {
  AttachmentMeta,
  DocumentTabSchema,
  PersonSummary,
} from '~/types/stock-pos/common'
import { useConfirm } from '~/composables/common/useConfirm'
import type { ExportRequest } from '~/types/stock-pos/export'

const props = withDefaults(defineProps<{
  tabs: DocumentTabSchema[]
  activeTab: string
  fieldValue: (key: string) => unknown
  setFieldValue: (key: string, value: unknown) => void | Promise<void>
  pending?: boolean
  saving?: boolean
  error?: string | null
  notFound?: boolean
  readOnly?: boolean
  canSave?: boolean
  saveLabel?: string
  showSave?: boolean
  showMetaRail?: boolean
  showTabs?: boolean
  showListNav?: boolean
  canNavigatePrevious?: boolean
  canNavigateNext?: boolean
  loadingListNavigation?: boolean
  listNavigationDirection?: 'previous' | 'next' | null
  listTo?: string
  isCreate?: boolean
  /** Force the wider document content shell (matches App Config settings width). */
  contentWide?: boolean
  attachments?: AttachmentMeta[]
  currentUser?: { id: string, name: string, email?: string }
  metaTitle?: string
  metaSubtitle?: string
  /** Module icon rendered in the meta rail record tile. */
  metaIcon?: string
  metaStatus?: string
  metaStage?: string
  metaOwner?: PersonSummary | null
  metaAssignee?: PersonSummary | null
  metaTags?: string[]
  metaCreatedAt?: string
  metaUpdatedAt?: string
  moreItems?: DropdownMenuItem[][]
  exporting?: boolean
  canExport?: boolean
  confirmSave?: boolean
  showCancel?: boolean
}>(), {
  pending: false,
  saving: false,
  error: null,
  notFound: false,
  readOnly: false,
  canSave: true,
  showSave: true,
  showMetaRail: false,
  showTabs: true,
  showListNav: false,
  canNavigatePrevious: false,
  canNavigateNext: false,
  loadingListNavigation: false,
  listNavigationDirection: null,
  isCreate: false,
  contentWide: false,
  attachments: () => [],
  metaTags: () => [],
  exporting: false,
  canExport: true,
  confirmSave: true,
  showCancel: false,
})

const emit = defineEmits<{
  'update:activeTab': [string]
  'update:attachments': [AttachmentMeta[]]
  save: []
  refresh: []
  navigatePrevious: []
  navigateNext: []
  export: [request: ExportRequest]
}>()

const { t } = useI18n()

const exportFields = computed(() => {
  if (!props.canExport) return []
  const fields = props.tabs.flatMap(tab =>
    tab.sections.flatMap(section =>
          section.fields
            .filter(field =>
              field.type !== 'secret'
              && field.type !== 'alert'
              && field.type !== 'line-table'
              && field.type !== 'uom-conversions'
              && field.type !== 'related-records'
              && field.type !== 'permission-matrix',
            )
        .map(field => ({
          label: field.label || t(field.labelKey),
          value: field.key,
        })),
    ),
  )
  return [...new Map(fields.map(field => [field.value, field])).values()]
})

const showForm = computed(() =>
  !props.notFound && !props.error && (!props.pending || props.tabs.length > 0),
)

const { confirm } = useConfirm()

const resolvedSaveLabel = computed(() =>
  props.saveLabel || (props.isCreate ? t('core.confirm.submit') : t('core.common.save')),
)

const scrollEl = ref<HTMLElement | null>(null)
const showScrollTop = ref(false)
/** Rail starts collapsed — the header panel icon opens/closes it on every breakpoint. */
const metaRailOpen = ref(false)

function toggleMetaRail() {
  metaRailOpen.value = !metaRailOpen.value
}

function onFormScroll() {
  showScrollTop.value = (scrollEl.value?.scrollTop ?? 0) > 240
}

function scrollToTop() {
  scrollEl.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

function selectTab(value: string) {
  emit('update:activeTab', value)
  scrollEl.value?.scrollTo({ top: 0 })
}

async function onSaveClick() {
  if (!props.confirmSave) {
    emit('save')
    return
  }
  const ok = await confirm({
    kind: props.isCreate ? 'submit' : 'save',
  })
  if (ok) emit('save')
}
</script>

<template>
  <div class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-default">
    <LayoutAppHeaderPageActions
      :can-create="false"
      :refreshing="pending"
      :more-items="moreItems"
      :export-fields="exportFields"
      :exporting="exporting"
      :show-list-nav="showListNav"
      :list-to="listTo"
      :can-navigate-previous="canNavigatePrevious"
      :can-navigate-next="canNavigateNext"
      :loading-list-navigation="loadingListNavigation"
      :list-navigation-direction="listNavigationDirection"
      :is-create="isCreate"
      :show-save="showSave && canSave && !readOnly"
      :save-label="resolvedSaveLabel"
      :saving="saving"
      :show-cancel="showCancel && Boolean(listTo)"
      :cancel-to="listTo"
      :show-meta-rail-toggle="showMetaRail && !notFound && !error && showForm"
      :meta-rail-open="metaRailOpen"
      @refresh="emit('refresh')"
      @export="emit('export', $event)"
      @navigate-previous="emit('navigatePrevious')"
      @navigate-next="emit('navigateNext')"
      @save="onSaveClick"
      @toggle-meta-rail="toggleMetaRail"
    >
      <template v-if="$slots.leading" #leading>
        <slot name="leading" />
      </template>
      <slot name="actions" />
    </LayoutAppHeaderPageActions>

    <div class="relative flex min-h-0 w-full min-w-0 flex-1 overflow-hidden p-0">
      <div
        v-if="pending"
        class="absolute inset-0 z-10 flex items-center justify-center bg-default/50 backdrop-blur-[1px]"
      >
        <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
      </div>

      <div class="relative flex min-h-0 w-full min-w-0 flex-1 overflow-hidden bg-default">
        <button
          v-if="metaRailOpen"
          type="button"
          class="absolute inset-0 z-20 bg-black/25 lg:hidden"
          :aria-label="t('actions.close')"
          @click="metaRailOpen = false"
        />

        <div class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <DocumentAppDocumentTabBar
            v-if="showTabs && showForm && !notFound && !error"
            :tabs="tabs"
            :active-tab="activeTab"
            @update:active-tab="selectTab"
          />

          <div
            ref="scrollEl"
            class="min-h-0 min-w-0 flex-1 overflow-auto"
            @scroll.passive="onFormScroll"
          >
            <UAlert
              v-if="notFound"
              class="mx-auto mt-6 w-full px-4 sm:px-6 lg:px-10"
              :class="contentWide
                ? 'max-w-5xl lg:max-w-6xl xl:max-w-7xl'
                : 'max-w-2xl sm:max-w-3xl lg:max-w-4xl'"
              color="error"
              :title="t('core.states.notFound')"
            />
            <UAlert
              v-else-if="error"
              class="mx-auto mt-6 w-full px-4 sm:px-6 lg:px-10"
              :class="contentWide
                ? 'max-w-5xl lg:max-w-6xl xl:max-w-7xl'
                : 'max-w-2xl sm:max-w-3xl lg:max-w-4xl'"
              color="error"
              :title="error"
            />

            <template v-else-if="showForm">
              <slot name="before-form" />

              <div
                class="flex min-h-0 w-full"
                :class="$slots.aside && !showMetaRail ? 'flex-col xl:flex-row' : 'flex-col'"
              >
                <div class="min-w-0 flex-1">
                  <slot name="form">
                    <DocumentAppDocumentForm
                      :tabs="tabs"
                      :active-tab="activeTab"
                      :field-value="fieldValue"
                      :set-field-value="setFieldValue"
                      :read-only="readOnly"
                      :wide="contentWide"
                    />
                  </slot>

                  <DocumentAppDocumentContentShell
                    v-if="$slots['after-form']"
                    :wide="contentWide"
                    class="space-y-3 pb-6"
                  >
                    <slot name="after-form" />
                  </DocumentAppDocumentContentShell>
                </div>

                <aside
                  v-if="$slots.aside && !showMetaRail"
                  class="w-full shrink-0 border-t border-default px-4 py-6 sm:px-6 xl:w-80 xl:border-t-0 xl:border-l xl:overflow-y-auto"
                >
                  <slot name="aside" />
                </aside>
              </div>
            </template>
          </div>

          <UButton
            v-show="showScrollTop && showForm"
            icon="i-lucide-chevron-up"
            color="neutral"
            variant="soft"
            size="sm"
            square
            class="absolute bottom-4 right-4 z-20 border border-default shadow-sm"
            :aria-label="t('core.document.scrollToTop')"
            @click="scrollToTop"
          />
        </div>

        <aside
          v-if="showMetaRail && !notFound && !error && showForm"
          class="absolute inset-y-0 end-0 z-30 w-[min(22rem,calc(100%-3rem))] bg-default shadow-xl transition-transform duration-200 lg:static lg:z-auto lg:w-64 lg:shadow-none xl:w-72"
          :class="metaRailOpen
            ? 'translate-x-0'
            : 'translate-x-full rtl:-translate-x-full lg:hidden'"
        >
          <UButton
            icon="i-lucide-x"
            color="neutral"
            variant="ghost"
            size="sm"
            square
            class="absolute end-2 top-2 z-10 lg:hidden"
            :aria-label="t('actions.close')"
            @click="metaRailOpen = false"
          />
          <DocumentAppDocumentMetaRail
            class="h-full min-h-0 overflow-y-auto"
            :title="metaTitle"
            :subtitle="metaSubtitle"
            :icon="metaIcon"
            :owner="metaOwner || undefined"
            :created-at="metaCreatedAt"
            :updated-at="metaUpdatedAt"
          />
        </aside>
      </div>
    </div>
  </div>
</template>
