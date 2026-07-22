import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerPaymentPage from '@/views/CustomerPaymentPage.vue'
import { getMockPaymentStatusApi } from '@/api/checkout'
import { VISION_PET_TASK_EVENT } from '@/utils/visionPet'


vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,qr') },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { token: 'payment-token' } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/api/checkout', () => ({
  createMockPaymentOrderApi: vi.fn(),
  getMockPaymentOrderApi: vi.fn(),
  getMockPaymentStatusApi: vi.fn(),
}))

const pendingOrder = {
  order_uuid: '53a80169-0000-0000-0000-000000000000',
  payment_token: 'payment-token',
  status: 'pending',
  amount: 37,
  item_count: 1,
  items: [{ class_id: 1, name: '测试商品', count: 1, subtotal: 37 }],
  created_at: '2026-07-22T10:00:00',
  expires_at: '2099-07-22T10:10:00',
}

let wrapper

describe('CustomerPaymentPage desktop pet checkout state', () => {
  beforeEach(() => {
    sessionStorage.clear()
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(pendingOrder))
    getMockPaymentStatusApi.mockReset().mockResolvedValue({
      status: 'paid',
      paid_at: '2026-07-22T10:01:00',
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('announces payment success when backend polling changes the order to paid', async () => {
    const events = []
    const listener = (event) => events.push(event.detail)
    window.addEventListener(VISION_PET_TASK_EVENT, listener)

    wrapper = mount(CustomerPaymentPage, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    window.removeEventListener(VISION_PET_TASK_EVENT, listener)
    expect(wrapper.text()).toContain('付款成功')
    expect(events).toContainEqual(
      expect.objectContaining({
        state: 'checkout',
        message: '支付成功 · ¥ 37.00',
      }),
    )
  })
})
