/** POS is a focused workspace: no left sidebar, header Back returns to the app. */

export function isPosPath(path: string) {
  return path === '/pos' || path.startsWith('/pos/')
}

export function isRememberableAppPath(path: string) {
  const clean = (path.split('?')[0] || '/').trim() || '/'
  if (isPosPath(clean)) return false
  if (clean.startsWith('/auth')) return false
  return true
}

export function usePosChrome() {
  const route = useRoute()
  const lastAppPath = useState('last-non-pos-path', () => '/')
  /** Checkout is a focused sell step — hide the sticky AppHeader. */
  const hidePosAppHeader = useState('pos-hide-app-header', () => false)
  const isPosWorkspace = computed(() => isPosPath(route.path))

  function rememberAppPath(path?: string) {
    const candidate = path || route.fullPath
    const clean = (candidate.split('?')[0] || '/').trim() || '/'
    if (!isRememberableAppPath(clean)) return
    lastAppPath.value = clean
  }

  function leavePos() {
    return navigateTo(lastAppPath.value || '/')
  }

  return {
    isPosWorkspace,
    hidePosAppHeader,
    lastAppPath,
    rememberAppPath,
    leavePos,
  }
}
