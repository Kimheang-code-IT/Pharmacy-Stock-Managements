import { DEFAULT_DOCUMENT_SEQUENCE_TYPES, DOCUMENT_SEQUENCE_STATUSES } from '~/utils/document-sequences'
import type { ModuleField, ModuleConfig } from './modules'
import { ACTIVE_STATUS } from './shared-options'

/** Administration modules for the Stock & POS system. */

type ModuleFieldType = ModuleField['type']
type ModuleSelectOption = string | { label: string, value: string }

const f = (
  key: string,
  label: string,
  labelKm: string,
  section = 'General Information',
  sectionKm = 'ព័ត៌មានទូទៅ',
  type: ModuleFieldType = 'text',
  options?: readonly ModuleSelectOption[] | ModuleSelectOption[],
  extra: Partial<ModuleField> = {},
): ModuleField => ({ key, label, labelKm, section, sectionKm, type, options, ...extra })

const col = (key: string, label: string, labelKm?: string, extra: Partial<ModuleField> = {}): ModuleField => ({
  key,
  label,
  labelKm: labelKm || label,
  ...extra,
})

function createModule(partial: Omit<ModuleConfig, 'canCreate'> & { canCreate?: boolean }): ModuleConfig {
  return {
    canCreate: partial.readOnly ? false : partial.canCreate !== false,
    kind: partial.kind || 'standard',
    ...partial,
  }
}

export const adminModules: ModuleConfig[] = [
  createModule({
    path: '/administration/users',
    title: 'Users',
    titleKm: 'អ្នកប្រើប្រាស់',
    singular: 'User',
    singularKm: 'អ្នកប្រើ',
    description: 'Manage staff access by role and department.',
    descriptionKm: 'គ្រប់គ្រងសិទ្ធិបុគ្គលិកតាមតួនាទី និងនាយកដ្ឋាន។',
    icon: 'i-lucide-users',
    group: 'admin',
    permission: 'user.view',
    actionPermissions: { create: 'user.create', edit: 'user.update', delete: 'user.delete' },
    collection: 'users',
    titleField: 'displayName',
    columns: [
      col('displayName', 'Display Name', 'ឈ្មោះបង្ហាញ'),
      col('email', 'Email', 'អ៊ីមែល'),
      col('role', 'Role', 'តួនាទី', { labelKey: 'core.fields.roleAssignments' }),
      col('telegramName', 'Telegram', 'Telegram'),
      col('status', 'Status', 'ស្ថានភាព'),
      col('lastLogin', 'Last Login', 'ចូលចុងក្រោយ'),
    ],
    fields: [
      // No username field: backend users authenticate with the email only, so
      // a typed username was silently dropped by adaptUserIn and the list then
      // showed an email-derived value — the "wrong data after save" bug.
      f('displayName', 'Display Name', 'ឈ្មោះបង្ហាញ', 'General', 'ទូទៅ', 'text', undefined, { required: true }),
      f('email', 'Email', 'អ៊ីមែល', 'General', 'ទូទៅ', 'text', undefined, { required: true }),
      f('password', 'Password', 'ពាក្យសម្ងាត់', 'General', 'ទូទៅ', 'password', undefined, {
        required: true,
        createOnly: true,
        helpKey: 'app.modules.users.fieldHelp.password',
      }),
      f('roleId', 'Role', 'តួនាទី', 'General', 'ទូទៅ', 'select', undefined, {
        required: true,
        labelKey: 'core.fields.roleAssignments',
        optionsEndpoint: '/api/v1/admin/roles/options',
        helpKey: 'app.modules.users.fieldHelp.roleId',
      }),
      f('telegramName', 'Telegram Name', 'ឈ្មោះ Telegram', 'Telegram', 'Telegram', 'text', undefined, {
        help: 'Label of the linked Telegram account, e.g. the person or @handle. Linked automatically through the bot, or edited here.',
      }),
      f('telegramChatId', 'Telegram Chat ID', 'លេខ Chat ID Telegram', 'Telegram', 'Telegram', 'text', undefined, {
        help: 'Private chat ID that receives notifications and password-reset codes. Enter it here to link manually; clear it to unlink.',
      }),
    ],
  }),
  createModule({
    path: '/administration/roles',
    title: 'Roles & Permissions',
    titleKm: 'តួនាទី និងសិទ្ធិ',
    singular: 'Role',
    singularKm: 'តួនាទី',
    description: 'Define module permissions for staff teams.',
    descriptionKm: 'កំណត់សិទ្ធិម៉ូឌុលសម្រាប់ក្រុមជួលម៉ូតូ។',
    icon: 'i-lucide-shield-check',
    group: 'admin',
    permission: 'role.view',
    actionPermissions: { create: 'role.create', edit: 'role.update', delete: 'role.delete' },
    collection: 'roles',
    documentForm: 'roles',
    titleField: 'name',
    columns: [
      col('name', 'Role name', 'ឈ្មោះតួនាទី', { labelKey: 'app.modules.roles.fields.name' }),
      col('description', 'Description', 'បរិយាយ', { labelKey: 'core.fields.description' }),
      col('userCount', 'Users', 'អ្នកប្រើ'),
      col('permissionCount', 'Permissions', 'សិទ្ធិ'),
      col('status', 'Status', 'ស្ថានភាព'),
    ],
    fields: [
      f('name', 'Role name', 'ឈ្មោះតួនាទី', 'Main information', 'ព័ត៌មានទូទៅ', 'text', undefined, {
        required: true,
        labelKey: 'app.modules.roles.fields.name',
      }),
      f('status', 'Status', 'ស្ថានភាព', 'Main information', 'ព័ត៌មានទូទៅ', 'select', ACTIVE_STATUS),
      f('description', 'Description', 'បរិយាយ', 'Main information', 'ព័ត៌មានទូទៅ', 'textarea', undefined, {
        colSpan: 2,
        labelKey: 'core.fields.description',
      }),
    ],
  }),
  createModule({
    path: '/administration/document-sequences',
    title: 'Document Sequences',
    titleKm: 'លំដាប់លេខឯកសារ',
    singular: 'Document Sequence',
    singularKm: 'លំដាប់ឯកសារ',
    description: 'Configure automatic numbering for each document type (Sale, Payment, Customer, etc.).',
    descriptionKm: 'កំណត់លេខស្វ័យប្រវត្តិសម្រាប់ប្រភេទឯកសារនីមួយៗ (លក់ ទូទាត់ អតិថិជន ជាដើម)។',
    icon: 'i-lucide-list-ordered',
    group: 'admin',
    permission: 'sequence.view',
    actionPermissions: { create: 'sequence.create', edit: 'sequence.update', delete: 'sequence.delete' },
    collection: 'documentSequences',
    titleField: 'documentType',
    canCreate: true,
    columns: [
      col('documentType', 'Document Type', 'ប្រភេទឯកសារ'),
      col('prefix', 'Prefix', 'បុព្វបទ'),
      col('paddingLength', 'Padding Length', 'ប្រវែងលេខ'),
      col('nextNumberPreview', 'Next Number Preview', 'លេខបន្ទាប់'),
      col('status', 'Status', 'ស្ថានភាព'),
    ],
    fields: [
      f('documentType', 'Document Type', 'ប្រភេទឯកសារ', 'General', 'ទូទៅ', 'select', DEFAULT_DOCUMENT_SEQUENCE_TYPES, {
        required: true,
        helpKey: 'core.fieldHelp.documentSequenceType',
      }),
      f('prefix', 'Prefix', 'បុព្វបទ', 'General', 'ទូទៅ', 'text', undefined, { required: true }),
      f('paddingLength', 'Padding Length', 'ប្រវែងលេខ', 'General', 'ទូទៅ', 'number', undefined, { required: true }),
      f('year', 'Year in number (optional)', 'ឆ្នាំក្នុងលេខ (ស្រេចចិត្ត)', 'General', 'ទូទៅ', 'number', undefined, {
        helpKey: 'core.fieldHelp.documentSequenceYear',
      }),
      f('nextNumberPreview', 'Next Number Preview', 'លេខបន្ទាប់', 'General', 'ទូទៅ', 'text', undefined, { computed: true }),
      f('status', 'Status', 'ស្ថានភាព', 'Status', 'ស្ថានភាព', 'select', DOCUMENT_SEQUENCE_STATUSES, { required: true }),
    ],
    filters: [
      f('documentType', 'Document Type', 'ប្រភេទឯកសារ', '', '', 'select'),
      f('status', 'Status', 'ស្ថានភាព', '', '', 'select', DOCUMENT_SEQUENCE_STATUSES),
    ],
  }),
  createModule({
    path: '/administration/audit-logs',
    title: 'Audit Logs',
    titleKm: 'កំណត់ហេតុសវនកម្ម',
    singular: 'Audit Log',
    singularKm: 'កំណត់ហេតុ',
    description: 'Trace create, update, approve, send and payment actions across the system.',
    descriptionKm: 'តាមដានសកម្មភាពបង្កើត កែប្រែ អនុម័ត ផ្ញើ និងទូទាត់។',
    icon: 'i-lucide-scroll-text',
    group: 'admin',
    permission: 'audit.view',
    collection: 'auditLogs',
    titleField: 'action',
    readOnly: true,
    tableOnly: true,
    columns: [
      col('occurredAt', 'Date / Time', 'កាលបរិច្ឆេទ / ពេលវេលា'),
      col('user', 'User', 'អ្នកប្រើ'),
      col('action', 'Action', 'សកម្មភាព'),
      col('result', 'Result', 'លទ្ធផល'),
      col('ipDevice', 'IP Device', 'ឧបករណ៍ IP'),
    ],
    fields: [
      f('occurredAt', 'Time', 'ពេលវេលា', 'Log', 'កំណត់ហេតុ', 'datetime'),
      f('user', 'User', 'អ្នកប្រើ', 'Log', 'កំណត់ហេតុ'),
      f('action', 'Action', 'សកម្មភាព', 'Log', 'កំណត់ហេតុ'),
      f('result', 'Result', 'លទ្ធផល', 'Result', 'លទ្ធផល'),
      f('ipDevice', 'IP Device', 'ឧបករណ៍ IP', 'Traceability', 'ការតាមដាន'),
      f('beforeData', 'Before Data', 'ទិន្នន័យមុន', 'Data', 'ទិន្នន័យ', 'textarea'),
      f('afterData', 'After Data', 'ទិន្នន័យបន្ទាប់', 'Data', 'ទិន្នន័យ', 'textarea'),
      f('metadata', 'Metadata', 'មេតាទិន្នន័យ', 'Data', 'ទិន្នន័យ', 'textarea'),
    ],
    filters: [
      f('user', 'Actor', 'អ្នកប្រើ', '', ''),
      f('result', 'Result', 'លទ្ធផល', '', '', 'select', ['SUCCESS', 'FAILED', 'DENIED']),
    ],
  }),
]

/** Field helper re-export keeps admin module field types explicit. */
export type { ModuleField }


