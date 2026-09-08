import { localStore } from '~/utils/storage/local'

const AuthKeys = {
  REMEMBER_EMAIL: 'login:remember:email',
  REMEMBER_ENABLED: 'login:remember:enabled',
} as const

export type RememberMeState = {
  enabled: boolean
  email: string
}

export function readRememberMe(): RememberMeState {
  const enabled = localStore.get(AuthKeys.REMEMBER_ENABLED) === '1'
  const email = enabled ? (localStore.get(AuthKeys.REMEMBER_EMAIL) || '') : ''
  return { enabled, email }
}

