import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import App from '@/App.vue'
import appRouter from '@/router'

const EmptyPage = { template: '<main />' }

describe('App', () => {
  it('does not mount VisionPet on routes that opt out', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/auth', component: EmptyPage, meta: { hideVisionPet: true } },
        { path: '/workspace', component: EmptyPage },
      ],
    })
    await router.push('/auth')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          VisionPet: { template: '<div data-testid="vision-pet-stub" />' },
        },
      },
    })

    expect(wrapper.find('[data-testid="vision-pet-stub"]').exists()).toBe(false)

    await router.push('/workspace')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="vision-pet-stub"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('marks login and register routes as pet-free', () => {
    expect(appRouter.resolve('/login').meta.hideVisionPet).toBe(true)
    expect(appRouter.resolve('/register').meta.hideVisionPet).toBe(true)
  })
})
