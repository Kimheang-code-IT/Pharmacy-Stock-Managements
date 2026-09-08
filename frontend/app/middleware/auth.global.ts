import { useAccessAlert } from '~/composables/common/useAccessAlert'
import { safeInternalPath } from '~/utils/auth/session'

const PERMITTED_LANDING_ROUTES = [
  ['/', 'dashboard.view'],
  ['/setup/categories', 'categories.view'],
  ['/setup/uoms', 'uom.view'],
  ['/setup/brands', 'brand.view'],
  ['/stock', 'products.view'],
  ['/setup/suppliers', 'suppliers.view'],
  ['/pos', 'pos.view'],
  ['/setup/customers', 'customers.view'],
  ['/reports/sales', 'reports.view'],
  ['/administration/users', 'admin.users.view'],
  ['/administration/settings', 'settings.app_config.view'],
] as const

export default defineNuxtRouteMiddleware((to, from) => {
  const auth = useAuthStore()
  const { showPermissionDenied } = useAccessAlert()

  if (import.meta.client && auth.user && !auth.hasSessionTokens()) {
    auth.clearSession()
  }

  const publicPaths = [
    '/auth/login',
    '/auth/setup',
    '/auth/forgot-password',
    '/auth/forget-password',
    '/auth/verify-code',
    '/auth/reset-password',
  ]
  const path = to.path.replace(/\/+$/, '') || '/'
  const isPublicPage = publicPaths.includes(path)

  if (!auth.isLoggedIn && !isPublicPage) {
    return navigateTo({
      path: '/auth/login',
      query: { redirect: to.fullPath },
    }, { replace: true })
  }

  if (auth.isLoggedIn && isPublicPage) {
    return navigateTo(safeInternalPath(to.query.redirect) || '/', { replace: true })
  }

  const permission = typeof to.meta.permission === 'string' ? to.meta.permission : ''
  if (auth.isLoggedIn && permission && !auth.canAccessPage(permission)) {
    showPermissionDenied({
      requestedPath: to.fullPath,
      permission,
    })

    // Keep the current authorized page when denial happens during navigation.
    if (from.matched.length && from.path !== to.path) return abortNavigation()

    // A direct URL needs an authorized page underneath the global dialog.
    const landing = PERMITTED_LANDING_ROUTES.find(([, required]) => auth.canAccessPage(required))
    if (landing) return navigateTo(landing[0], { replace: true })

    // An account with no usable page returns to sign-in without creating a denial page.
    auth.clearSession()
    return navigateTo('/auth/login', { replace: true })
  }
})
