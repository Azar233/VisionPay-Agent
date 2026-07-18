import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AgentConfirmationCard from '@/components/AgentConfirmationCard.vue'

const mocks = vi.hoisted(() => ({
  confirm: vi.fn(),
  get: vi.fn(),
  rotate: vi.fn(),
  cancel: vi.fn(),
  petUpdate: vi.fn(),
  petFinish: vi.fn(),
  beginPet: vi.fn(),
}))

vi.mock('@/api/agentOperations', () => ({
  confirmAgentOperationApi: mocks.confirm,
  getAgentOperationApi: mocks.get,
  rotateAgentOperationTokenApi: mocks.rotate,
  cancelAgentOperationApi: mocks.cancel,
}))

vi.mock('@/utils/visionPet', () => ({
  beginVisionPetTask: mocks.beginPet,
}))

const stubs = {
  ElTag: { template: '<span><slot /></span>' },
  ElIcon: { template: '<span><slot /></span>' },
  WarningFilled: { template: '<i />' },
  CircleCheckFilled: { template: '<i />' },
  ElButton: {
    props: ['disabled', 'loading'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('AgentConfirmationCard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mocks.beginPet.mockReturnValue({ update: mocks.petUpdate, finish: mocks.petFinish })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('polls confirmed dataset operations and forwards real progress to the pet', async () => {
    const confirmation = deferred()
    const operation = {
      operation_uuid: 'derive-operation-1',
      action: 'dataset.derive',
      status: 'pending',
      risk_level: 'R2',
      confirmation_token: 'token-with-at-least-twenty-characters',
      impact: { title: '派生数据集版本', summary: '创建派生草稿' },
    }
    mocks.get
      .mockResolvedValueOnce({ ...operation })
      // 确认前的状态同步仍然返回 pending，流程才会继续。
      .mockResolvedValueOnce({ ...operation })
      .mockResolvedValue({
        ...operation,
        status: 'executing',
        task_progress: { status: 'running', progress: 54, message: '正在复制数据集文件' },
      })
    mocks.confirm.mockReturnValue(confirmation.promise)

    const wrapper = mount(AgentConfirmationCard, {
      props: { operation },
      global: { stubs },
    })
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await vi.advanceTimersByTimeAsync(120)
    await flushPromises()

    expect(mocks.beginPet).toHaveBeenCalledWith(expect.objectContaining({ showProgress: true }))
    expect(mocks.petUpdate).toHaveBeenCalledWith({
      message: '派生数据集版本：正在复制数据集文件',
      progress: 54,
    })

    confirmation.resolve({
      ...operation,
      status: 'completed',
      result: { id: 3 },
      task_progress: {
        status: 'completed',
        progress: 100,
        history: [
          { progress: 72, message: '正在创建版本映射' },
          { progress: 96, message: '正在计算内容指纹' },
          { progress: 100, message: '数据集操作已完成' },
        ],
      },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()

    expect(mocks.petUpdate).toHaveBeenCalledWith({
      message: '派生数据集版本：正在计算内容指纹',
      progress: 96,
    })
    expect(mocks.petFinish).toHaveBeenCalledWith(expect.objectContaining({ progress: 100 }))
    wrapper.unmount()
  })

  it('waits for non-progress confirmations (e.g. price update) instead of failing early', async () => {
    const confirmation = deferred()
    const operation = {
      operation_uuid: 'price-op-1',
      action: 'catalog.update_price',
      status: 'pending',
      risk_level: 'R2',
      confirmation_token: 'token-with-at-least-twenty-characters',
      impact: { title: '更新商品价格', summary: '商品价格将从 3.5 改为 13.5 CNY' },
    }
    mocks.get.mockResolvedValue({ ...operation })
    mocks.confirm.mockReturnValue(confirmation.promise)

    const wrapper = mount(AgentConfirmationCard, {
      props: { operation },
      global: { stubs },
    })
    await flushPromises()
    await wrapper.get('button').trigger('click')

    // 请求未返回期间不得误报“操作执行未返回结果”。
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()
    expect(mocks.petFinish).not.toHaveBeenCalled()
    expect(operation.error_message).toBeFalsy()

    confirmation.resolve({ ...operation, status: 'completed', result: { updated: true } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()

    expect(mocks.petFinish).toHaveBeenCalledWith(expect.objectContaining({ progress: 100 }))
    expect(operation.status).toBe('completed')
    wrapper.unmount()
  })
})
