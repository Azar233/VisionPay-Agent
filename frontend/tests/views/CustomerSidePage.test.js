import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CustomerSidePage from '@/views/CustomerSidePage.vue'

describe('CustomerSidePage', () => {
  it('在新窗口打开 5174 用户侧', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mount(CustomerSidePage, {
      global: {
        stubs: {
          'el-icon': { template: '<span><slot /></span>' },
        },
      },
    })

    await wrapper.get('.launch-button').trigger('click')

    expect(open).toHaveBeenCalledWith(
      'http://localhost:5174/checkout',
      '_blank',
      'noopener,noreferrer',
    )
    open.mockRestore()
  })
})
