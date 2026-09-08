import { describe, expect, it } from 'vitest'
import { isPosPath, isRememberableAppPath } from '../app/composables/layout/usePosChrome'

describe('POS chrome paths', () => {
  it('treats /pos and nested POS routes as the POS workspace', () => {
    expect(isPosPath('/pos')).toBe(true)
    expect(isPosPath('/pos/')).toBe(true)
    expect(isPosPath('/stock')).toBe(false)
    expect(isPosPath('/')).toBe(false)
  })

  it('remembers in-app pages but not POS or auth', () => {
    expect(isRememberableAppPath('/stock')).toBe(true)
    expect(isRememberableAppPath('/reports/finance?q=1')).toBe(true)
    expect(isRememberableAppPath('/pos')).toBe(false)
    expect(isRememberableAppPath('/auth/login')).toBe(false)
  })
})
