import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearPersistedCustomerMode,
  persistCustomerMode,
  resolveCustomerModeNavigation,
} from '@/utils/customerMode'

describe('customer mode navigation lock', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('allows checkout and payment but redirects other pages while customer mode is active', () => {
    localStorage.setItem('vp_agent_user', JSON.stringify({ id: 7 }))
    localStorage.setItem('vp_agent_token', 'token')
    persistCustomerMode(7)

    expect(resolveCustomerModeNavigation({ path: '/checkout' })).toBe(true)
    expect(resolveCustomerModeNavigation({ path: '/checkout/payment' })).toBe(true)
    expect(
      resolveCustomerModeNavigation({
        path: '/mock-pay/payment-token',
        meta: { customerModeAllowed: true },
      }),
    ).toBe(true)
    expect(resolveCustomerModeNavigation({ path: '/dashboard' })).toBe('/checkout')
    expect(resolveCustomerModeNavigation({ path: '/checkout/history' })).toBe('/checkout')
  })

  it('releases the navigation lock after customer mode is cleared', () => {
    localStorage.setItem('vp_agent_user', JSON.stringify({ id: 7 }))
    persistCustomerMode(7)
    clearPersistedCustomerMode()

    expect(resolveCustomerModeNavigation({ path: '/dashboard' }, 'token')).toBe(true)
  })
})
