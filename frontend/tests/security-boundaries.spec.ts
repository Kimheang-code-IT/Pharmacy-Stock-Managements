import { describe, expect, it } from 'vitest'
import { compactQuery } from '../app/utils/api/query'
import { safeInternalPath } from '../app/utils/auth/session'
import { safeApiBase, safeExternalUrl, sameOriginApiUrl } from '../app/utils/security/url'

describe('security boundaries', () => {
  it('accepts only safe internal redirects', () => {
    expect(safeInternalPath('/stock/123')).toBe('/stock/123')
    expect(safeInternalPath('//evil.example')).toBeNull()
    expect(safeInternalPath('/auth/login')).toBeNull()
    expect(safeInternalPath('/stock\u0000/123')).toBeNull()
  })

  it('rejects executable and credential-bearing external URLs', () => {
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(safeExternalUrl('https://user:secret@example.com/file')).toBeNull()
    expect(safeExternalUrl('https://example.com/file')).toBe('https://example.com/file')
  })

  it('requires HTTPS for a production API base', () => {
    expect(safeApiBase('http://localhost:8000', false)).toBe('http://localhost:8000')
    expect(safeApiBase('http://api.example.com', true)).toBeNull()
    expect(safeApiBase('https://api.example.com/', true)).toBe('https://api.example.com')
  })

  it('prevents requests from escaping the configured API origin', () => {
    expect(sameOriginApiUrl('/api/v1/products', 'https://api.example.com')).toBe('https://api.example.com/api/v1/products')
    expect(sameOriginApiUrl('https://evil.example/products', 'https://api.example.com')).toBeNull()
  })

  it('removes empty query values without changing valid filters', () => {
    expect(compactQuery({ q: 'widget', empty: '', none: null, page: 1, status: [] })).toEqual({ q: 'widget', page: 1 })
  })
})
