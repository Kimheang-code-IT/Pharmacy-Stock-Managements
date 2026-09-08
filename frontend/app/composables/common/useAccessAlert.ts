export type AccessAlertKind = 'permission' | 'session-expired'

type AccessAlertState = {
  open: boolean
  kind: AccessAlertKind
  permission: string
  requestedPath: string
  description: string
}

/** App-wide access/session alert state shared by route guards and API requests. */
export function useAccessAlert() {
  const state = useState<AccessAlertState>('app-access-alert', () => ({
    open: false,
    kind: 'permission',
    permission: '',
    requestedPath: '',
    description: '',
  }))

  function showPermissionDenied(options: {
    permission?: string
    requestedPath?: string
    description?: string
  } = {}) {
    state.value = {
      open: true,
      kind: 'permission',
      permission: options.permission || '',
      requestedPath: options.requestedPath || '',
      description: options.description || '',
    }
  }

  function showSessionExpired(description = '') {
    state.value = {
      open: true,
      kind: 'session-expired',
      permission: '',
      requestedPath: '',
      description,
    }
  }

  function close() {
    state.value.open = false
  }

  return {
    state,
    showPermissionDenied,
    showSessionExpired,
    close,
  }
}
