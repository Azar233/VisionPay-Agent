import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VisionPet from '@/components/VisionPet.vue'
import { useVisionPetStore } from '@/stores/visionPet'
import { notifyVisionPetTask } from '@/utils/visionPet'

describe('VisionPet', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('starts idle and responds to task events', async () => {
    const wrapper = mount(VisionPet, {
      global: { plugins: [createPinia()] },
    })
    expect(wrapper.attributes('aria-label')).toContain('待机状态')
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetTask({
      state: 'checkout',
      message: '订单正在确认',
      duration: 0,
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('订单正在确认')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('100%')
    expect(useVisionPetStore().state).toBe('checkout')
    wrapper.unmount()
  })

  it('stops dragging when pointer release happens outside the pet', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })

    await wrapper.trigger('pointerdown', {
      button: 0,
      clientX: 100,
      clientY: 100,
      pointerId: 7,
    })
    expect(wrapper.classes()).toContain('is-dragging')

    window.dispatchEvent(new Event('pointerup'))
    await wrapper.vm.$nextTick()

    expect(wrapper.classes()).not.toContain('is-dragging')
    expect(localStorage.getItem('vp_vision_pet_position')).toBeTruthy()
    wrapper.unmount()
  })
})
