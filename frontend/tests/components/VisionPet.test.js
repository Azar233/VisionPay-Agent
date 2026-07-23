import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VisionPet from '@/components/VisionPet.vue'
import { useVisionPetStore } from '@/stores/visionPet'
import {
  beginVisionPetTask,
  notifyVisionPetBackendError,
  notifyVisionPetPaymentSuccess,
  notifyVisionPetTask,
  notifyVisionPetTaskProgress,
  VISION_PET_TASK_EVENT,
} from '@/utils/visionPet'

describe('VisionPet', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 768 })
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

  it('plays checkout success and returns to idle after the payment message', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetPaymentSuccess({ amount: 37, duration: 1200 })
    await wrapper.vm.$nextTick()

    expect(useVisionPetStore().state).toBe('checkout')
    expect(wrapper.classes()).toContain('is-checkout')
    expect(wrapper.text()).toContain('支付成功 · ¥ 37.00')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('100%')

    vi.advanceTimersByTime(1200)
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('idle')
    expect(wrapper.text()).not.toContain('支付成功')
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

  it('opens the message toward the viewport when the pet is at the top-left edge', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 640 })
    localStorage.setItem('vp_vision_pet_position', JSON.stringify({ x: 16, y: 16 }))

    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    const bubbleList = wrapper.get('.pet-message-list')
    Object.defineProperty(bubbleList.element, 'offsetWidth', { configurable: true, value: 240 })
    Object.defineProperty(bubbleList.element, 'offsetHeight', { configurable: true, value: 70 })

    notifyVisionPetTask({ state: 'working', message: '正在处理任务', duration: 0 })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(bubbleList.classes()).toContain('opens-right')
    expect(bubbleList.classes()).toContain('opens-below')
    expect(Number.parseFloat(bubbleList.element.style.left)).toBeGreaterThanOrEqual(0)
    expect(Number.parseFloat(bubbleList.element.style.top)).toBeGreaterThanOrEqual(0)
    wrapper.unmount()
  })

  it('resizes the pet while keeping position and sprite dimensions in sync', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()

    useVisionPetStore().setSizePercent(120)
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(wrapper.attributes('style')).toContain('width: 160.8px')
    expect(wrapper.attributes('style')).toContain('height: 217.2px')
    expect(wrapper.attributes('style')).toContain('--pet-stage-width: 134.4px')
    expect(wrapper.find('.pet-stage').exists()).toBe(true)
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
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain(
      'visionpay-pet-working-v1.png',
    )
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('400% 100%')
    expect(wrapper.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('37')
    expect(wrapper.find('.pet-progress span').attributes('style')).toContain('37%')
    expect(wrapper.attributes('aria-label')).toContain('进度 37%')

    notifyVisionPetTaskProgress({ status: 'completed', message: '任务完成', duration: 0 })
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('idle')
    wrapper.unmount()
  })

  it('maps failed backend tasks to the error sequence and returns to idle', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    notifyVisionPetTaskProgress({
      status: 'failed',
      message: '派生数据集失败',
      duration: 1200,
    })
    await wrapper.vm.$nextTick()

    expect(useVisionPetStore().state).toBe('error')
    expect(wrapper.classes()).toContain('is-error')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('visionpay-pet-error-v1.png')
    expect(wrapper.find('.pet-sprite').attributes('style')).toContain('400% 100%')
    expect(wrapper.attributes('aria-label')).toContain('派生数据集失败')

    vi.advanceTimersByTime(1200)
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('idle')
    expect(wrapper.text()).not.toContain('派生数据集失败')
    wrapper.unmount()
  })

  it('only reports unexpected backend and network failures', () => {
    const updates = []
    const listener = (event) => updates.push(event.detail)
    window.addEventListener(VISION_PET_TASK_EVENT, listener)

    expect(
      notifyVisionPetBackendError({
        response: { status: 422, data: { message: '参数验证失败' } },
      }),
    ).toBe(false)
    expect(
      notifyVisionPetBackendError({
        response: { status: 503, data: { message: '知识库构建失败' } },
      }),
    ).toBe(true)
    expect(notifyVisionPetBackendError(new Error('网络已断开'))).toBe(true)

    window.removeEventListener(VISION_PET_TASK_EVENT, listener)
    expect(updates).toEqual([
      expect.objectContaining({ state: 'error', message: '知识库构建失败' }),
      expect.objectContaining({ state: 'error', message: '网络已断开' }),
    ])
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

    const task = beginVisionPetTask({
      message: '正在创建派生版本',
      progress: 0,
      showProgress: true,
    })
    task.update({ message: '正在复制数据集文件', progress: 64 })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('正在复制数据集文件')
    expect(useVisionPetStore().tasks[0].progress).toBe(64)
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
    expect(wrapper.text()).toContain('正在准备数据')
    expect(wrapper.text()).toContain('正在执行检测')
    expect(wrapper.findAll('.pet-message')).toHaveLength(2)

    firstTask.finish()
    await wrapper.vm.$nextTick()
    expect(useVisionPetStore().state).toBe('working')
    expect(wrapper.text()).not.toContain('正在准备数据')
    expect(wrapper.text()).toContain('正在执行检测')
    expect(wrapper.findAll('.pet-message')).toHaveLength(1)

    secondTask.finish()
    expect(useVisionPetStore().state).toBe('idle')
    wrapper.unmount()
  })

  it('shows the latest two task bubbles and summarizes additional concurrent tasks', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(VisionPet, { global: { plugins: [pinia] } })
    await wrapper.vm.$nextTick()
    await Promise.resolve()

    const firstTask = beginVisionPetTask({ message: '任务一' })
    const secondTask = beginVisionPetTask({ message: '任务二' })
    const thirdTask = beginVisionPetTask({ message: '任务三' })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).not.toContain('任务一')
    expect(wrapper.text()).toContain('任务二')
    expect(wrapper.text()).toContain('任务三')
    expect(wrapper.text()).toContain('还有 1 个任务正在执行')
    expect(wrapper.findAll('.pet-message')).toHaveLength(2)

    firstTask.finish()
    secondTask.finish()
    thirdTask.finish()
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
