import { beforeEach, describe, expect, it, vi } from 'vitest'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))

vi.mock('@/router', () => ({
  default: {
    currentRoute: { value: { path: '/detection', fullPath: '/detection?tab=agent' } },
    replace,
  },
}))

import { streamChat } from '@/utils/stream'

describe('streamChat', () => {
  beforeEach(() => {
    localStorage.clear()
    replace.mockClear()
    vi.restoreAllMocks()
  })

  it('clears login state and redirects when SSE returns 401', async () => {
    localStorage.setItem('vp_agent_token', 'expired-token')
    localStorage.setItem('vp_agent_user', '{"id":1}')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401, ok: false }))
    const onError = vi.fn()

    const stream = streamChat('/api/chat/stream', { message: '你好' }, { onError })
    await stream.completion

    expect(localStorage.getItem('vp_agent_token')).toBeNull()
    expect(localStorage.getItem('vp_agent_user')).toBeNull()
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: '登录已过期，请重新登录' }))
    expect(replace).toHaveBeenCalledWith({
      path: '/login',
      query: { redirect: '/detection?tab=agent' },
    })
  })
})
