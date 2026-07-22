import { describe, expect, it } from 'vitest'
import { resolveAuthNavigation } from '@/router'

describe('authentication navigation', () => {
  it('sends unauthenticated workspace navigation through the Vision login journey', () => {
    const result = resolveAuthNavigation(
      {
        path: '/dashboard',
        fullPath: '/dashboard',
        name: 'Dashboard',
        query: {},
        matched: [{ meta: { requiresAuth: true } }],
      },
      '',
    )

    expect(result).toEqual({
      path: '/welcome',
      query: {
        redirect: '/dashboard',
        entry: 'awakening',
      },
    })
  })

  it('allows the legacy login path to reach its compatibility redirect', () => {
    const result = resolveAuthNavigation(
      {
        path: '/login',
        fullPath: '/login',
        name: 'Login',
        query: {},
        matched: [{ meta: { requiresAuth: false } }],
      },
      '',
    )

    expect(result).toBe(true)
  })

  it('opens the final login chapter for an authenticated replay without looping', () => {
    const result = resolveAuthNavigation(
      {
        path: '/welcome',
        fullPath: '/welcome?entry=awakening&redirect=/dashboard',
        name: 'VisionJourney',
        query: { entry: 'awakening', redirect: '/dashboard' },
        matched: [{ meta: { requiresAuth: false } }],
      },
      'test-token',
    )

    expect(result).toEqual({
      path: '/welcome',
      query: {
        entry: 'core',
        redirect: '/dashboard',
      },
    })

    expect(
      resolveAuthNavigation(
        {
          path: '/welcome',
          fullPath: '/welcome?entry=core&redirect=/dashboard',
          name: 'VisionJourney',
          query: { entry: 'core', redirect: '/dashboard' },
          matched: [{ meta: { requiresAuth: false } }],
        },
        'test-token',
      ),
    ).toBe(true)
  })
})
