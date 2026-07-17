import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPage from '@/views/ChatPage.vue'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { getChatSessionApi, getChatSessionsApi } from '@/api/chat'
import { loginApi } from '@/api/auth'

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

vi.mock('@/api/chat', () => ({
  createChatSessionApi: vi.fn(),
  deleteChatSessionApi: vi.fn(),
  getAgentStatusApi: vi.fn().mockResolvedValue({ configured: true, agents: [] }),
  getChatSessionApi: vi.fn(),
  getChatSessionsApi: vi.fn().mockResolvedValue({ items: [] }),
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
    vi.clearAllMocks()
    getChatSessionsApi.mockResolvedValue({ items: [] })
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

  it('preserves unsent text and attachments across route navigation', async () => {
    const agentStore = useAgentStore()
    const file = new File(['image'], 'draft.jpg', { type: 'image/jpeg' })
    agentStore.draftText = '这段文字还没有发送'
    agentStore.draftAttachments = [{ id: 'draft-file', file, preview: '' }]

    const first = shallowMount(ChatPage, {
      global: { directives: { loading: () => {} } },
    })
    await flushPromises()
    first.unmount()

    expect(agentStore.draftText).toBe('这段文字还没有发送')
    expect(agentStore.draftAttachments).toHaveLength(1)

    const second = shallowMount(ChatPage, {
      global: { directives: { loading: () => {} } },
    })
    await flushPromises()

    expect(second.find('textarea').element.value).toBe('这段文字还没有发送')
    expect(second.text()).toContain('draft.jpg')
  })

  it('shows a new conversation on first entry instead of opening recent history', async () => {
    getChatSessionsApi.mockResolvedValue({
      items: [{ session_uuid: 'recent-session', title: '上一次对话' }],
    })

    const wrapper = shallowMount(ChatPage, {
      global: { directives: { loading: () => {} } },
    })
    await flushPromises()

    const agentStore = useAgentStore()
    expect(agentStore.currentSessionId).toBeNull()
    expect(agentStore.messages).toEqual([])
    expect(getChatSessionApi).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('今天想处理什么？')
    expect(wrapper.text()).toContain('上一次对话')
  })

  it('clears the previous active conversation after a new login succeeds', async () => {
    const agentStore = useAgentStore()
    agentStore.currentSessionId = 'previous-login-session'
    agentStore.messages = [{ role: 'user', content: '上次登录的消息' }]
    agentStore.draftText = '上次登录的草稿'
    loginApi.mockResolvedValue({
      access_token: 'new-token',
      user: { id: 2, username: 'new-user' },
    })

    await useUserStore().login({ username: 'new-user', password: 'secret' })

    expect(agentStore.currentSessionId).toBeNull()
    expect(agentStore.messages).toEqual([])
    expect(agentStore.draftText).toBe('')
  })
})
