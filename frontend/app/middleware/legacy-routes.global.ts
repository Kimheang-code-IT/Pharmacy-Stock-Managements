/**
 * Temporary redirects from the legacy flat master-data routes to their
 * `/setup/*` replacements (see docs/PAGE_ROUTE_MAP.md migration note).
 * Remove once old bookmarks and external links have migrated.
 */
const LEGACY_SETUP_PREFIXES = [
  '/categories',
  '/uoms',
  '/suppliers',
  '/customers',
] as const

/** Removed pages that now redirect to their replacement. */
const REMOVED_PREFIXES: Record<string, string> = {
  '/brands': '/stock/products',
  '/setup/brands': '/stock/products',
}

export default defineNuxtRouteMiddleware((to) => {
  const path = to.path.replace(/\/+$/, '') || '/'

  const removedTo = Object.entries(REMOVED_PREFIXES).find(
    ([prefix]) => path === prefix || path.startsWith(`${prefix}/`),
  )?.[1]
  if (removedTo) {
    return navigateTo({ path: removedTo, query: to.query, hash: to.hash }, { replace: true })
  }

  const isLegacy = LEGACY_SETUP_PREFIXES.some(
    prefix => path === prefix || path.startsWith(`${prefix}/`),
  )
  if (!isLegacy) return

  return navigateTo(
    { path: `/setup${path}`, query: to.query, hash: to.hash },
    { replace: true },
  )
})
