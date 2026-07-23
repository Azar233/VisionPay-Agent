import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerModeExitControl from '@/components/checkout/CustomerModeExitControl.vue'
import { verifyCustomerModePassword } from '@/api/user'
import { useCustomerModeStore } from '@/stores/customerMode'

vi.mock('@/api/user', () => ({
  verifyCustomerModePassword: vi.fn(),
}))

describe('CustomerModeExitControl', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('uses the touch keypad and exits only after password verification', async () => {
    verifyCustomerModePassword.mockResolvedValue({ valid: true })
    const pinia = createPinia()
    setActivePinia(pinia)
    const customerModeStore = useCustomerModeStore()
    customerModeStore.enter(3)

    const wrapper = mount(CustomerModeExitControl, {
      attachTo: document.body,
      global: {
        plugins: [pinia, ElementPlus],
        stubs: { teleport: true },
      },
    })
    await wrapper.get('.customer-mode-exit-button').trigger('click')
    await wrapper.vm.$nextTick()

    for (const digit of ['6', '5', '4', '3', '2', '1']) {
      const key = wrapper.findAll('.touch-keypad button').find((button) => button.text() === digit)
      await key.trigger('click')
    }
    const verify = wrapper.findAll('button').find((button) => button.text().includes('验证并退出'))
    await verify.trigger('click')
    await flushPromises()

    expect(verifyCustomerModePassword).toHaveBeenCalledWith('654321')
    expect(customerModeStore.enabled).toBe(false)
    wrapper.unmount()
  })
})
