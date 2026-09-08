/**
 * Temporary redirects from the legacy flat master-data routes to their
 * `/setup/*` replacements (see docs/PAGE_ROUTE_MAP.md migration note).
 * Remove once old bookmarks and external links have migrated.
 */
const LEGACY_SETUP_PREFIXES = [
  '/categories',
  '/uoms',
  '/brands',
  '/suppliers',
  '/customers',
] as const

export default defineNuxtRouteMiddleware((to) => {
  const path = to.path.replace(/\/+$/, '') || '/'
  const isLegacy = LEGACY_SETUP_PREFIXES.some(
    prefix => path === prefix || path.startsWith(`${prefix}/`),
  )
  if (!isLegacy) return

  return navigateTo(
    { path: `/setup${path}`, query: to.query, hash: to.hash },
    { replace: true },
  )
})
