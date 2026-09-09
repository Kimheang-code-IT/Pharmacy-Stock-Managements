import type { ModuleConfig, ModuleField } from './modules'
import { DELIVERY_STATUSES } from '~/utils/delivery/notes'

/**
 * Delivery Notes module (spec §2.1.9 / §5.13). Rendered by the dedicated
 * delivery-notes pages; the config registers navigation metadata, column
 * labels and the status vocabulary for search, i18n and shared lookups.
 */

const f = (
  key: string,
  label: string,
  section = 'Delivery Information',
  type: ModuleField['type'] = 'text',
  options?: ModuleField['options'],
  extra: Partial<ModuleField> = {},
): ModuleField => ({ key, label, labelKm: label, section, sectionKm: section, type, options, ...extra })

const col = (key: string, label: string, extra: Partial<ModuleField> = {}): ModuleField => ({
  key,
  label,
  labelKm: label,
  ...extra,
})

export const deliveryModules: ModuleConfig[] = [
  {
    canCreate: true,
    kind: 'standard',
    path: '/delivery-notes',
    title: 'Delivery Notes',
    titleKm: 'លិខិតបញ្ជូនទំនិញ',
    singular: 'Delivery Note',
    singularKm: 'លិខិតបញ្ជូនទំនិញ',
    description: 'Track product delivery to clients from confirmed sales. Partial deliveries are allowed and no stock is moved again.',
    descriptionKm: 'តាមដានការបញ្ជូនទំនិញទៅអតិថិជនពីការលក់ដែលបានបញ្ជាក់។ អាចបញ្ជូនបានម្តងមិនទាល់តែសោះ ហើយស្តុកមិនធ្លាក់ម្តងទៀតទេ។',
    icon: 'i-lucide-package-check',
    group: 'master',
    permission: 'delivery.view',
    collection: 'deliveryNotes',
    titleField: 'deliveryNo',
    statuses: DELIVERY_STATUSES,
    columns: [
      col('deliveryNo', 'Delivery No'),
      col('invoiceNo', 'Invoice / Sale No'),
      col('customer', 'Customer'),
      col('deliveryPhone', 'Phone'),
      col('createdAt', 'Date', { type: 'date' }),
      col('status', 'Status'),
      col('itemCount', 'Items', { type: 'number' }),
    ],
    // Metadata only — delivery data comes from POS sales; there is no
    // contact/driver/schedule form (spec §5.13: table + Delivery OK status).
    fields: [
      f('saleId', 'Sale', 'General Information', 'select', undefined, { required: true, createOnly: true, help: 'POS sale that this delivery fulfills.' }),
      f('status', 'Status', 'Status', 'select', DELIVERY_STATUSES, { computed: true }),
    ],
    filters: [
      f('status', 'Status', '', 'select', DELIVERY_STATUSES),
      f('customer', 'Customer', '', 'select'),
    ],
  },
]
