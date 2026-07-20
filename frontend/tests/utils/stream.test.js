import { beforeEach, describe, expect, it, vi } from 'vitest'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))

vi.mock('@/router', () => ({
  default: {
    currentRoute: { value: { path: '/chat', fullPath: '/chat' } },
    replace,
  },
}))

import { streamChat } from '@/utils/stream'
import { VISION_PET_TASK_EVENT } from '@/utils/visionPet'

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
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: '登录已过期，请重新登录' }),
    )
    expect(replace).toHaveBeenCalledWith({
      path: '/login',
      query: { redirect: '/chat' },
    })
  })

  it('maps backend SSE lifecycle events to working and idle pet states', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      encoder.encode(
        [
          'data: {"type":"routing","agent":"detection"}',
          '',
          'data: {"type":"tool_call","tool":"detect_products"}',
          '',
          'data: {"type":"text_chunk","content":"完成"}',
          '',
          'data: [DONE]',
          '',
        ].join('\n'),
      ),
    ]
    let chunkIndex = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        body: {
          getReader: () => ({
            read: async () =>
              chunkIndex < chunks.length
                ? { done: false, value: chunks[chunkIndex++] }
                : { done: true, value: undefined },
          }),
        },
      }),
    )
    const updates = []
    const listener = (event) => updates.push(event.detail)
    window.addEventListener(VISION_PET_TASK_EVENT, listener)

    const onDone = vi.fn()
    const stream = streamChat('/api/chat/stream', { message: '识别商品' }, { onDone })
    await stream.completion
    window.removeEventListener(VISION_PET_TASK_EVENT, listener)

    expect(onDone).toHaveBeenCalledOnce()
    expect(updates).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ state: 'working', message: 'Agent 正在处理任务' }),
        expect.objectContaining({ state: 'working', message: '检测智能体正在处理' }),
        expect.objectContaining({ state: 'working', message: '正在执行 detect_products' }),
        expect.objectContaining({ state: 'idle', message: '回答完成', duration: 3200 }),
      ]),
    )
    expect(updates.at(-1).state).toBe('idle')
    expect(updates.at(-1).message).toBe('回答完成')
  })

  it('maps backend SSE error events to the pet error state', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      encoder.encode(
        [
          'data: {"type":"routing","agent":"knowledge"}',
          '',
          'data: {"type":"error","content":"Agent 处理失败"}',
          '',
          'data: [DONE]',
          '',
        ].join('\n'),
      ),
    ]
    let chunkIndex = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        body: {
          getReader: () => ({
            read: async () =>
              chunkIndex < chunks.length
                ? { done: false, value: chunks[chunkIndex++] }
                : { done: true, value: undefined },
          }),
        },
      }),
    )
    const updates = []
    const listener = (event) => updates.push(event.detail)
    window.addEventListener(VISION_PET_TASK_EVENT, listener)

    const stream = streamChat('/api/chat/stream', { message: '检索知识库' })
    await stream.completion
    window.removeEventListener(VISION_PET_TASK_EVENT, listener)

    expect(updates.at(-1)).toEqual(
      expect.objectContaining({
        state: 'error',
        message: '任务处理失败',
        duration: 3200,
      }),
    )
  })
})
