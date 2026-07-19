import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useUserStore } from '@/stores/user'


describe('user display name', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('prefers nickname and falls back to the login username', () => {
    const store = useUserStore()

    store.setUser({ username: 'operator', nickname: '小蓝' })
    expect(store.displayName).toBe('小蓝')

    store.setUser({ username: 'operator', nickname: '' })
    expect(store.displayName).toBe('operator')
  })
})
