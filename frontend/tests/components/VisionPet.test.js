import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VisionPet from '@/components/VisionPet.vue'
import { useVisionPetStore } from '@/stores/visionPet'
import {
  beginVisionPetTask,
  notifyVisionPetTask,
  notifyVisionPetTaskProgress,
} from '@/utils/visionPet'

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

  it('maps backend task progress to the working sequence', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetTaskProgress({
      status: 'running',
      message: '正在分析任务',
      progress: 37,
      showProgress: true,
      duration: 0,
    })
    await wrapper.vm.$nextTick()

    expect(useVisionPetStore().state).toBe('working')
    expect(wrapper.attributes('aria-label')).toContain('正在分析任务')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('visionpay-pet-working-v1.png')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('400% 100%')
    expect(wrapper.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('37')
    expect(wrapper.find('.pet-progress span').attributes('style')).toContain('37%')
    expect(wrapper.attributes('aria-label')).toContain('进度 37%')

    notifyVisionPetTaskProgress({ status: 'completed', message: '任务完成', duration: 0 })
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('idle')
    wrapper.unmount()
  })

  it('does not show a progress bar for normal chat task events', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetTaskProgress({
      status: 'running',
      message: '知识智能体正在处理',
      duration: 0,
    })
    // A stray numeric value must not opt a normal chat task into progress UI.
    useVisionPetStore().progress = 42
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('知识智能体正在处理')
    expect(wrapper.text()).not.toContain('%')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.attributes('aria-label')).not.toContain('进度')
    wrapper.unmount()
  })

  it('updates task lease progress and clears it after the completion message', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    const task = beginVisionPetTask({ message: '正在创建派生版本', progress: 0, showProgress: true })
    task.update({ message: '正在复制数据集文件', progress: 64 })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('正在复制数据集文件')
    expect(useVisionPetStore().progress).toBe(64)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(true)

    task.finish({ message: '派生版本已完成', progress: 100, duration: 1200 })
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('idle')
    expect(useVisionPetStore().progress).toBe(100)

    vi.advanceTimersByTime(1200)
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().progress).toBeNull()
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('stays working until all concurrent task leases finish', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    const firstTask = beginVisionPetTask({ message: '正在准备数据' })
    const secondTask = beginVisionPetTask({ message: '正在执行检测' })
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('working')
    expect(wrapper.text()).toContain('正在执行检测')

    firstTask.finish()
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('working')
    expect(wrapper.text()).toContain('正在执行检测')

    secondTask.finish()
    expect(useVisionPetStore().state).toBe('idle')
    wrapper.unmount()
  })

  it('shows a completion message briefly after returning to idle', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetTaskProgress({
      status: 'completed',
      message: '回答完成',
      duration: 3200,
    })
    await wrapper.vm.$nextTick()

    expect(useVisionPetStore().state).toBe('idle')
    expect(wrapper.text()).toContain('回答完成')

    vi.advanceTimersByTime(3200)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('回答完成')
    wrapper.unmount()
  })
})
