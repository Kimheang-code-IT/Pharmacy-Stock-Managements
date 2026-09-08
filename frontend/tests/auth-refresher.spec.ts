import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createAuthRefresher } from '../app/utils/api/auth-refresher'

interface Harness {
  posts: Array<{ url: string, body: Record<string, unknown> }>
  sessionExpired: number
  accessTokens: Array<string | null>
}

function createHarness(overrides?: {
  refreshToken?: string | null
  post?: (url: string, body: Record<string, unknown>) => Promise<{ accessToken?: string }>
}) {
  const harness: Harness = { posts: [], sessionExpired: 0, accessTokens: [] }
  const refresher = createAuthRefresher({
    refreshEndpoint: '/api/v1/auth/refresh',
    getRefreshToken: () => overrides?.refreshToken !== undefined ? overrides.refreshToken : 'refresh-token',
    setAccessToken: (token) => {
      harness.accessTokens.push(token)
    },
    onSessionExpired: () => {
      harness.sessionExpired += 1
    },
    post: async (url, body) => {
      harness.posts.push({ url, body })
      if (overrides?.post) return overrides.post(url, body)
      return { data: { accessToken: 'new-access-token' } }
    },
  })
  return { refresher, harness }
}

beforeEach(() => {
  vi.useFakeTimers()
})

describe('createAuthRefresher', () => {
  it('rotates the token and stores the new access token', async () => {
    const { refresher, harness } = createHarness()
    const ok = await refresher.rotate()
    expect(ok).toBe(true)
    expect(harness.posts).toHaveLength(1)
    expect(harness.posts[0]?.url).toBe('/api/v1/auth/refresh')
    expect(harness.posts[0]?.body).toEqual({ refreshToken: 'refresh-token' })
    expect(harness.accessTokens).toEqual(['new-access-token'])
    expect(harness.sessionExpired).toBe(0)
  })

  it('shares one rotation request across concurrent callers (single-flight)', async () => {
    const { refresher, harness } = createHarness()
    const [a, b, c] = await Promise.all([
      refresher.rotate(),
      refresher.rotate(),
      refresher.rotate(),
    ])
    expect(a).toBe(true)
    expect(b).toBe(true)
    expect(c).toBe(true)
    expect(harness.posts).toHaveLength(1)
  })

  it('clears the session exactly once when the refresh request fails', async () => {
    const { refresher, harness } = createHarness({
      post: async () => {
        throw new Error('refresh rejected')
      },
    })
    const [a, b] = await Promise.all([refresher.rotate(), refresher.rotate()])
    expect(a).toBe(false)
    expect(b).toBe(false)
    expect(harness.sessionExpired).toBe(1)
    expect(harness.accessTokens).toHaveLength(0)
  })

  it('clears the session when no refresh token exists', async () => {
    const { refresher, harness } = createHarness({ refreshToken: null })
    const ok = await refresher.rotate()
    expect(ok).toBe(false)
    expect(harness.sessionExpired).toBe(1)
    expect(harness.posts).toHaveLength(0)
  })

  it('clears the session when the response has no access token', async () => {
    const { refresher, harness } = createHarness({ post: async () => ({}) })
    const ok = await refresher.rotate()
    expect(ok).toBe(false)
    expect(harness.sessionExpired).toBe(1)
  })

  it('allows a new rotation after the in-flight slot is released', async () => {
    const { refresher, harness } = createHarness()
    await refresher.rotate()
    await vi.runAllTimersAsync()
    await refresher.rotate()
    expect(harness.posts).toHaveLength(2)
  })
})

describe('single retry-after-refresh semantics', () => {
  it('retries the original request at most once after a successful rotation', async () => {
    const { refresher, harness } = createHarness()
    let executions = 0

    async function requestWithAuthRetry() {
      executions += 1
      const failed = executions === 1
      if (failed) {
        const rotated = await refresher.rotate()
        if (!rotated) return 'cleared'
        executions += 1
        return 'retried-ok'
      }
      return 'ok'
    }

    const result = await requestWithAuthRetry()
    expect(result).toBe('retried-ok')
    expect(executions).toBe(2)
    expect(harness.posts).toHaveLength(1)
  })

  it('does not retry when rotation fails', async () => {
    const { refresher, harness } = createHarness({
      post: async () => {
        throw new Error('reuse detected')
      },
    })
    let executions = 0

    async function requestWithAuthRetry() {
      executions += 1
      const rotated = await refresher.rotate()
      if (!rotated) return 'cleared'
      executions += 1
      return 'retried-ok'
    }

    const result = await requestWithAuthRetry()
    expect(result).toBe('cleared')
    expect(executions).toBe(1)
    expect(harness.sessionExpired).toBe(1)
  })
})

