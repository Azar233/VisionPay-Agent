import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'

const { replace, currentRoute } = vi.hoisted(() => ({
  replace: vi.fn(),
  currentRoute: { value: { path: '/dashboard', fullPath: '/dashboard?range=7d' } },
}))

vi.mock('@/router', () => ({
  default: { currentRoute, replace },
}))

import { handleAuthExpired, resetAuthExpiryState } from '@/utils/authExpiry'

describe('auth expiry handling', () => {
  beforeEach(() => {
    localStorage.clear()
    replace.mockClear()
    ElMessage.error.mockClear()
    resetAuthExpiryState()
    currentRoute.value = { path: '/dashboard', fullPath: '/dashboard?range=7d' }
  })

  it('coalesces concurrent 401 responses into one notification and redirect', () => {
    localStorage.setItem('vp_agent_token', 'expired-token')
    localStorage.setItem('vp_agent_user', '{"id":1}')
    const clearSession = vi.fn()

    expect(handleAuthExpired({ clearSession })).toBe(true)
    expect(handleAuthExpired({ clearSession })).toBe(false)
    expect(handleAuthExpired({ clearSession })).toBe(false)

    expect(clearSession).toHaveBeenCalledOnce()
    expect(ElMessage.error).toHaveBeenCalledOnce()
    expect(localStorage.getItem('vp_agent_token')).toBeNull()
    expect(localStorage.getItem('vp_agent_user')).toBeNull()
    expect(replace).toHaveBeenCalledOnce()
    expect(replace).toHaveBeenCalledWith({
      path: '/login',
      query: { redirect: '/dashboard?range=7d' },
    })
  })

  it('can handle a later expiration after a successful login resets the guard', () => {
    handleAuthExpired()
    resetAuthExpiryState()

    expect(handleAuthExpired()).toBe(true)
    expect(ElMessage.error).toHaveBeenCalledTimes(2)
    expect(replace).toHaveBeenCalledTimes(2)
  })
})
