<script setup lang="ts">
import type { DocumentTabSchema } from '~/types/stock-pos/common'
import { moduleDocumentRecordKey } from '~/utils/module/document-tabs'
import { documentFormItemKey, documentFormSectionItems } from '~/utils/module/form-layout'

const props = withDefaults(defineProps<{
  tabs: DocumentTabSchema[]
  activeTab: string
  fieldValue: (key: string) => unknown
  setFieldValue: (key: string, value: unknown) => void
  readOnly?: boolean
  /** Force wider shell even without dense field types. */
  wide?: boolean
}>(), {
  readOnly: false,
  wide: false,
})

const { t, te } = useI18n()

provide(moduleDocumentRecordKey, {
  get: (key: string) => props.fieldValue(key),
  set: (key: string, value: unknown) => { props.setFieldValue(key, value) },
})

function sectionHeading(section: DocumentTabSchema['sections'][0]) {
  if (section.titleKey && te(section.titleKey)) return t(section.titleKey)
  return section.title || ''
}

function sectionDescription(section: DocumentTabSchema['sections'][0]) {
  if (section.descriptionKey && te(section.descriptionKey)) return t(section.descriptionKey)
  return section.description || ''
}

const wideForm = computed(() =>
  props.wide
  || props.tabs.some(tab =>
    tab.sections.some(section =>
      section.fields.some(field =>
        field.type === 'notification-rules'
        || field.type === 'line-table'
        || field.type === 'uom-conversions'
        || field.type === 'related-records',
      ),
    ),
  ),
)

function isFullWidthField(field: DocumentTabSchema['sections'][0]['fields'][0]) {
  return field.colSpan === 2
    || field.type === 'textarea'
    || field.type === 'permission-matrix'
    || field.type === 'notification-rules'
    || field.type === 'connection-status'
    || field.type === 'alert'
    || field.type === 'line-table'
    || field.type === 'uom-conversions'
    || field.type === 'related-records'
}

const sectionItems = (fields: DocumentTabSchema['sections'][0]['fields']) =>
  documentFormSectionItems(fields)

const itemKey = (item: ReturnType<typeof documentFormSectionItems>[number], index: number) =>
  documentFormItemKey(item, index)
</script>

<template>
  <div class="min-w-0 w-full flex-1 overflow-x-hidden">
    <DocumentAppDocumentContentShell :wide="wideForm">
      <template v-for="tab in tabs" :key="tab.id">
        <div v-show="activeTab === tab.id || tabs.length === 1" class="space-y-8 py-6">
          <section
            v-for="(section, sectionIndex) in tab.sections"
            :key="section.id"
            class="space-y-4"
            :class="sectionIndex > 0 ? 'border-t border-default pt-6' : ''"
          >
            <div v-if="sectionHeading(section) || sectionDescription(section)">
              <h3 v-if="sectionHeading(section)" class="text-sm font-medium text-highlighted">
                {{ sectionHeading(section) }}
              </h3>
              <p v-if="sectionDescription(section)" class="mt-1 text-xs text-muted">
                {{ sectionDescription(section) }}
              </p>
            </div>

            <div class="grid min-w-0 grid-cols-1 gap-x-5 gap-y-5 sm:grid-cols-2">
              <template
                v-for="(item, itemIndex) in sectionItems(section.fields)"
                :key="itemKey(item, itemIndex)"
              >
                <!-- Image pair: normal fields stacked left, compact upload right (sm+) -->
                <div
                  v-if="item.kind === 'image-pair'"
                  class="grid min-w-0 grid-cols-1 gap-x-5 gap-y-5 sm:col-span-2 sm:grid-cols-2"
                >
                  <div class="min-w-0 space-y-5">
                    <DocumentAppDynamicFieldRenderer
                      v-for="leftField in item.left"
                      :key="leftField.key"
                      :field="leftField"
                      :model-value="fieldValue(leftField.key)"
                      :disabled="readOnly || Boolean(leftField.readOnly)"
                      @update:model-value="(v) => setFieldValue(leftField.key, v)"
                    />
                  </div>
                  <DocumentAppDynamicFieldRenderer
                    :field="item.image"
                    :model-value="fieldValue(item.image.key)"
                    :disabled="readOnly || Boolean(item.image.readOnly)"
                    @update:model-value="(v) => setFieldValue(item.image.key, v)"
                  />
                </div>
                <div
                  v-else
                  class="min-w-0 max-w-full"
                  :class="isFullWidthField(item.field) ? 'sm:col-span-2' : ''"
                >
                  <DocumentAppDynamicFieldRenderer
                    :field="item.field"
                    :model-value="fieldValue(item.field.key)"
                    :disabled="readOnly || Boolean(item.field.readOnly)"
                    @update:model-value="(v) => setFieldValue(item.field.key, v)"
                  />
                </div>
              </template>
            </div>
          </section>
        </div>
      </template>
    </DocumentAppDocumentContentShell>
  </div>
</template>
