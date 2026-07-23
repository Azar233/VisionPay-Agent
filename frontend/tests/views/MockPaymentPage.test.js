import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MockPaymentPage from '@/views/MockPaymentPage.vue'
import { confirmMockPaymentApi, getMockPaymentOrderApi } from '@/api/checkout'
import { VISION_PET_TASK_EVENT } from '@/utils/visionPet'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: 'payment-token' } }),
}))

vi.mock('@/api/checkout', () => ({
  confirmMockPaymentApi: vi.fn(),
  getMockPaymentOrderApi: vi.fn(),
}))

const pendingOrder = {
  order_uuid: '53a80169-0000-0000-0000-000000000000',
  status: 'pending',
  amount: 37,
  item_count: 1,
  items: [{ class_id: 1, name: '测试商品', count: 1, unit_price: 37, subtotal: 37 }],
  expires_at: '2099-07-22T10:10:00',
}

let wrapper

describe('MockPaymentPage desktop pet checkout state', () => {
  beforeEach(() => {
    getMockPaymentOrderApi.mockReset().mockResolvedValue(pendingOrder)
    confirmMockPaymentApi.mockReset().mockResolvedValue({ ...pendingOrder, status: 'paid' })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('shows working while confirming and checkout after payment succeeds', async () => {
    const events = []
    const listener = (event) => events.push(event.detail)
    window.addEventListener(VISION_PET_TASK_EVENT, listener)

    wrapper = mount(MockPaymentPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.get('.confirm-button').trigger('click')
    await flushPromises()

    window.removeEventListener(VISION_PET_TASK_EVENT, listener)
    expect(wrapper.text()).toContain('模拟付款成功')
    expect(events).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ state: 'working', message: '正在确认支付' }),
        expect.objectContaining({ state: 'checkout', message: '支付成功 · ¥ 37.00' }),
      ]),
    )
  })
})
