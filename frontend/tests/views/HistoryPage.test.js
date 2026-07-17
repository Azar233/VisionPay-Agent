import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HistoryPage from '@/views/HistoryPage.vue'
import { getHistoryOverview } from '@/api/history'

vi.mock('@/api/history', () => ({
  deleteTask: vi.fn(), getAgentCallDetail: vi.fn(), getAgentCallList: vi.fn(),
  getHistoryOverview: vi.fn(), getModelHistoryDetail: vi.fn(), getModelHistoryList: vi.fn(),
  getScenes: vi.fn(), getTaskDetail: vi.fn(), getTaskList: vi.fn(),
}))

const tabsStub = {
  name: 'ElTabs',
  emits: ['tab-change'],
  template: '<div data-test="tabs"><slot /></div>',
}
const paneStub = {
  name: 'ElTabPane',
  template: '<section><slot name="label" /><slot /></section>',
}

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getHistoryOverview.mockResolvedValue({
      detection_tasks: 12,
      agent_calls: 8,
      today_agent_calls: 3,
      models: 4,
      active_models: 2,
    })
  })

  it('loads the unified overview and starts with detection history only', async () => {
    const wrapper = shallowMount(HistoryPage, {
      global: {
        stubs: {
          ElTabs: tabsStub,
          ElTabPane: paneStub,
          DetectionHistoryPanel: { name: 'DetectionHistoryPanel', template: '<div data-test="detection-panel" />' },
          AgentHistoryPanel: { name: 'AgentHistoryPanel', template: '<div data-test="agent-panel" />' },
          ModelHistoryPanel: { name: 'ModelHistoryPanel', template: '<div data-test="model-panel" />' },
        },
      },
    })
    await flushPromises()

    expect(getHistoryOverview).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('识别任务12')
    expect(wrapper.text()).toContain('Agent 调用8')
    expect(wrapper.find('[data-test="detection-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="agent-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="model-panel"]').exists()).toBe(false)
  })

  it('lazily mounts Agent and model history after their tabs are selected', async () => {
    const wrapper = shallowMount(HistoryPage, {
      global: {
        stubs: {
          ElTabs: tabsStub,
          ElTabPane: paneStub,
          DetectionHistoryPanel: { name: 'DetectionHistoryPanel', template: '<div data-test="detection-panel" />' },
          AgentHistoryPanel: { name: 'AgentHistoryPanel', template: '<div data-test="agent-panel" />' },
          ModelHistoryPanel: { name: 'ModelHistoryPanel', template: '<div data-test="model-panel" />' },
        },
      },
    })
    await flushPromises()

    wrapper.findComponent(tabsStub).vm.$emit('tab-change', 'agent')
    await flushPromises()
    expect(wrapper.find('[data-test="agent-panel"]').exists()).toBe(true)

    wrapper.findComponent(tabsStub).vm.$emit('tab-change', 'model')
    await flushPromises()
    expect(wrapper.find('[data-test="model-panel"]').exists()).toBe(true)
  })
})
