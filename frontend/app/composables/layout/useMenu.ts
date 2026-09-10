import type { NavigationMenuItem } from '@nuxt/ui'

const SIDEBAR_COLLAPSED_KEY = 'stock-pos:sidebar:collapsed'
const SIDEBAR_AUTO_MQ = '(max-width: 1023px)'

/** Single source of truth for Stock & POS navigation. */
export function useMenu() {
  const { t } = useI18n()
  const open = useState('sidebar-open', () => false)
  const collapsed = useState('sidebar-collapsed', () => false)
  const manualCollapsed = useState<boolean | null>('sidebar-collapsed-manual', () => null)
  const isNarrow = useMediaQuery(SIDEBAR_AUTO_MQ)
  const hydrated = useState('sidebar-collapsed-hydrated', () => false)

  function close() { open.value = false }
  function applyAutoCollapse(narrow: boolean) { collapsed.value = manualCollapsed.value == null ? narrow : manualCollapsed.value }
  function setCollapsed(value: boolean) {
    collapsed.value = value
    manualCollapsed.value = value
    if (import.meta.client) localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? '1' : '0')
  }

  onMounted(() => {
    if (hydrated.value) return
    hydrated.value = true
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    if (saved === '1' || saved === '0') {
      manualCollapsed.value = saved === '1'
      collapsed.value = manualCollapsed.value
    }
    else applyAutoCollapse(isNarrow.value)
    watch(isNarrow, applyAutoCollapse)
  })

  const pageLink = (label: string, to: string): NavigationMenuItem => ({ label, to, exact: true, class: 'text-sm gap-2', onSelect: close })

  const ROUTE_PERMISSION: Record<string, string> = {
    '/': 'dashboard.view',
    '/stock': 'products.view',
    '/pos': 'pos.view',
    '/delivery-notes': 'delivery.view',
    '/setup/categories': 'categories.view',
    '/setup/uoms': 'uom.view',
    '/setup/brands': 'brand.view',
    '/setup/suppliers': 'suppliers.view',
    '/setup/customers': 'customers.view',
    '/reports/sales': 'reports.view',
    '/reports/purchases': 'reports.view',
    '/reports/customer-debts': 'reports.view',
    '/reports/supplier-debts': 'reports.view',
    '/reports/finance': 'reports.view',
    '/administration/users': 'admin.users.view',
    '/administration/roles': 'admin.roles.view',
    '/administration/document-sequences': 'configuration.view',
    '/administration/settings': 'settings.app_config.view',
    '/administration/audit-logs': 'admin.audit_logs.view',
  }

  const auth = useAuthStore()

  function canSee(to: string) {
    const permission = ROUTE_PERMISSION[to]
    if (!permission) return true
    return auth.canAccessPage(permission)
  }

  function filterItem(item: NavigationMenuItem): NavigationMenuItem | null {
    if (item.children?.length) {
      const children = item.children.map(filterItem).filter((child): child is NavigationMenuItem => Boolean(child))
      if (!children.length) return null
      return { ...item, children }
    }
    const to = typeof item.to === 'string' ? item.to : ''
    return canSee(to) ? item : null
  }

  const group = (id: string, label: string, icon: string, children: NavigationMenuItem[]): NavigationMenuItem => ({
    label,
    icon,
    type: 'trigger',
    value: id,
    defaultOpen: true,
    class: 'mt-1 text-sm gap-2',
    children,
  })

  const links = computed<NavigationMenuItem[][]>(() => {
    const tree: NavigationMenuItem[] = [
      { label: t('app.nav.dashboard'), icon: 'i-lucide-layout-dashboard', to: '/', exact: true, class: 'text-sm gap-2', onSelect: close },
      { label: t('app.nav.stock'), icon: 'i-lucide-package', to: '/stock', class: 'text-sm gap-2', onSelect: close },
      { label: t('app.nav.pos'), icon: 'i-lucide-store', to: '/pos', class: 'text-sm gap-2', onSelect: close },
      { label: t('app.nav.deliveryNotes'), icon: 'i-lucide-package-check', to: '/delivery-notes', class: 'text-sm gap-2', onSelect: close },
      group('setup', t('app.nav.setup'), 'i-lucide-settings-2', [
        pageLink(t('app.nav.categories'), '/setup/categories'),
        pageLink(t('app.nav.uoms'), '/setup/uoms'),
        pageLink(t('app.nav.brands'), '/setup/brands'),
        pageLink(t('app.nav.suppliers'), '/setup/suppliers'),
        pageLink(t('app.nav.customers'), '/setup/customers'),
      ]),
      group('reports', t('app.nav.reports'), 'i-lucide-bar-chart-3', [
        pageLink(t('app.pages.salesReport'), '/reports/sales'),
        pageLink(t('app.pages.purchaseReport'), '/reports/purchases'),
        pageLink(t('app.pages.customerReturns'), '/reports/customer-returns'),
        pageLink(t('app.pages.supplierReturns'), '/reports/supplier-returns'),
        pageLink(t('app.pages.customerDebtReport'), '/reports/customer-debts'),
        pageLink(t('app.pages.supplierDebtReport'), '/reports/supplier-debts'),
        pageLink(t('app.pages.financeReport'), '/reports/finance'),
      ]),
      group('administration', t('app.nav.administration'), 'i-lucide-shield-check', [
        pageLink(t('app.pages.users'), '/administration/users'),
        pageLink(t('app.pages.roles'), '/administration/roles'),
        pageLink(t('app.pages.documentSequences'), '/administration/document-sequences'),
        pageLink(t('app.pages.auditLogs'), '/administration/audit-logs'),
        pageLink(t('app.pages.settings'), '/administration/settings'),
      ]),
    ]
    return [tree.map(filterItem).filter((item): item is NavigationMenuItem => Boolean(item)), []]
  })

  return { open, collapsed, links, close, setCollapsed }
}
