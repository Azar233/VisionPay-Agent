import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPage from '@/views/ChatPage.vue'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useRouter: () => ({
      currentRoute: { value: { fullPath: '/chat' } },
      push: vi.fn(),
    }),
  }
})

vi.mock('@/api/detection', () => ({
  createDetectionSessionApi: vi.fn(),
  deleteDetectionSessionApi: vi.fn(),
  detectBatchApi: vi.fn(),
  detectSingleApi: vi.fn(),
  detectVideoApi: vi.fn(),
  detectZipApi: vi.fn(),
  getAgentStatusApi: vi.fn().mockResolvedValue({ configured: true, agents: [] }),
  getDetectionSessionApi: vi.fn(),
  getDetectionSessionsApi: vi.fn().mockResolvedValue({ items: [] }),
  getVideoStatusApi: vi.fn(),
  saveDetectionExchangeApi: vi.fn(),
  uploadChatFilesApi: vi.fn(),
}))

vi.mock('@/api/agentOperations', () => ({
  cancelAgentOperationApi: vi.fn(),
  confirmAgentOperationApi: vi.fn(),
  getAgentOperationApi: vi.fn(),
  listAgentOperationsApi: vi.fn().mockResolvedValue({ items: [] }),
  rotateAgentOperationTokenApi: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  getUserInfoApi: vi.fn(),
  loginApi: vi.fn(),
}))

describe('ChatPage background navigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('preserves the active stream and messages when the route unmounts', async () => {
    const agentStore = useAgentStore()
    const abortStream = vi.fn()
    const activeMessages = [
      { role: 'user', content: '你好' },
      { role: 'assistant', content: '', loading: true },
    ]
    agentStore.currentSessionId = 'session-running'
    agentStore.messages = activeMessages
    agentStore.isLoading = true
    agentStore.abortController = abortStream

    const wrapper = shallowMount(ChatPage, {
      global: {
        directives: { loading: () => {} },
      },
    })
    await flushPromises()
    wrapper.unmount()

    expect(abortStream).not.toHaveBeenCalled()
    expect(agentStore.currentSessionId).toBe('session-running')
    expect(agentStore.messages).toEqual(activeMessages)
    expect(agentStore.isLoading).toBe(true)
  })

  it('still aborts and clears the background stream on logout', () => {
    const agentStore = useAgentStore()
    const abortStream = vi.fn()
    agentStore.currentSessionId = 'session-running'
    agentStore.messages = [{ role: 'assistant', content: '', loading: true }]
    agentStore.isLoading = true
    agentStore.abortController = abortStream

    useUserStore().logout()

    expect(abortStream).toHaveBeenCalledOnce()
    expect(agentStore.currentSessionId).toBeNull()
    expect(agentStore.messages).toEqual([])
    expect(agentStore.isLoading).toBe(false)
  })
})
