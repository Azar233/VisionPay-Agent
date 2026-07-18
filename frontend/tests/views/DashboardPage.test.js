import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardPage from '@/views/DashboardPage.vue'
import { getClassDistribution, getModelUsage, getStatistics, getTrend, getTypeDistribution } from '@/api/dashboard'

const { chart } = vi.hoisted(() => ({ chart: { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() } }))
vi.mock('echarts/core', () => ({ getInstanceByDom: vi.fn(() => null), init: vi.fn(() => chart), use: vi.fn() }))
vi.mock('echarts/charts', () => ({ BarChart: {}, LineChart: {}, PieChart: {} }))
vi.mock('echarts/components', () => ({ GraphicComponent: {}, GridComponent: {}, LegendComponent: {}, TooltipComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('@/api/dashboard', () => ({
  getClassDistribution: vi.fn(),
  getModelUsage: vi.fn(),
  getStatistics: vi.fn(),
  getTrend: vi.fn(),
  getTypeDistribution: vi.fn(),
}))

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    getStatistics.mockResolvedValue({ total_tasks: 2, total_images: 3, total_objects: 4, avg_inference_time: 20, growth: {} })
    getTrend.mockResolvedValue({ trend: [], granularity: 'day' })
    getClassDistribution.mockResolvedValue({ distribution: [] })
    getTypeDistribution.mockResolvedValue({ distribution: [] })
    getModelUsage.mockResolvedValue({
      summary: { total_calls: 2, total_turns: 1, total_tokens: 120, avg_latency_ms: 900, success_rate: 100 },
      trend: [],
      agent_distribution: [{ name: 'Dataset Agent', agent: 'dataset', value: 2 }],
      recent: [{
        id: 1, created_at: '2026-07-18T12:00:00', model_name: 'deepseek-chat', agent: 'dataset',
        agent_label: 'Dataset Agent', call_count: 2, input_tokens: 100, output_tokens: 20,
        total_tokens: 120, latency_ms: 900, status: 'completed',
      }],
    })
  })

  it('removes scene overview and renders model and Agent call data', async () => {
    const wrapper = mount(DashboardPage, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('业务场景')
    expect(wrapper.text()).toContain('模型调用')
    expect(wrapper.text()).toContain('deepseek-chat')
    expect(wrapper.text()).toContain('Dataset Agent')
    expect(wrapper.findAll('.el-tabs__item')).toHaveLength(2)
    expect(getModelUsage).toHaveBeenCalledWith(30, 8)
    expect(chart.setOption.mock.calls.some(([option]) => option.legend?.orient === 'vertical')).toBe(true)
    expect(chart.setOption.mock.calls.some(([option]) => option.series?.[0]?.center?.[0] === '34%')).toBe(true)
  })

  it('refreshes all recognition aggregates when the one-day range is selected', async () => {
    const wrapper = mount(DashboardPage, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    const range = wrapper.findAll('button').find((item) => item.text().trim() === '1 天')
    expect(range).toBeTruthy()
    await range.trigger('click')
    await flushPromises()
    expect(getTrend).toHaveBeenLastCalledWith({ days: 1, hours: 24, bucketHours: 2 })
    expect(getStatistics).toHaveBeenLastCalledWith(1)
    expect(getClassDistribution).toHaveBeenLastCalledWith(1)
    expect(getTypeDistribution).toHaveBeenLastCalledWith(1)
  })
})
