import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SettingsPage from '@/views/SettingsPage.vue'
import {
  getAgentInstructions,
  getCustomerModePasswordStatus,
  updateAgentInstructions,
  updateCustomerModePassword,
  updateProfile,
} from '@/api/user'

vi.mock('@/api/auth', () => ({
  getUserInfoApi: vi.fn().mockResolvedValue({
    username: 'operator',
    nickname: '',
    email: 'operator@example.com',
    phone: '',
    avatar: '',
    roles: ['operator'],
    created_at: '2026-01-01T00:00:00',
    last_login_at: null,
  }),
}))

vi.mock('@/api/user', () => ({
  changePassword: vi.fn(),
  getAgentInstructions: vi.fn(),
  getCustomerModePasswordStatus: vi.fn(),
  updateAgentInstructions: vi.fn(),
  updateCustomerModePassword: vi.fn(),
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
}))

describe('SettingsPage Agent 自定义指令', () => {
  beforeEach(() => {
    getAgentInstructions.mockReset().mockResolvedValue({
      instructions: '始终使用中文回答',
      max_length: 4000,
    })
    updateAgentInstructions.mockReset().mockImplementation(async (instructions) => ({
      message: instructions ? 'Agent 自定义指令已更新' : 'Agent 自定义指令已清除',
      instructions: instructions.trim(),
      max_length: 4000,
    }))
    updateProfile.mockReset().mockResolvedValue({
      user: {
        username: 'operator',
        nickname: '小蓝',
        email: 'operator@example.com',
        phone: '',
        avatar: '',
        created_at: '2026-01-01T00:00:00',
      },
    })
    getCustomerModePasswordStatus.mockReset().mockResolvedValue({
      configured: false,
      uses_default: true,
    })
    updateCustomerModePassword.mockReset().mockResolvedValue({
      message: '顾客展示模式退出密码已更新',
      configured: true,
      uses_default: false,
    })
  })

  it('loads, edits, saves and clears the user-scoped instructions', async () => {
    const wrapper = mount(SettingsPage, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await flushPromises()

    const instructionsTab = wrapper
      .findAll('button')
      .find((button) => button.text().includes('自定义指令'))
    await instructionsTab.trigger('click')

    const textarea = wrapper.get('textarea[aria-label="Agent 自定义指令"]')
    expect(textarea.element.value).toBe('始终使用中文回答')
    expect(textarea.attributes('maxlength')).toBe('4000')

    await textarea.setValue('先给结论，再使用 Markdown 表格')
    const save = wrapper.findAll('button').find((button) => button.text().trim() === '保存')
    await save.trigger('click')
    await flushPromises()
    expect(updateAgentInstructions).toHaveBeenLastCalledWith('先给结论，再使用 Markdown 表格')

    const clear = wrapper.findAll('button').find((button) => button.text().trim() === '清除指令')
    await clear.trigger('click')
    await flushPromises()
    expect(updateAgentInstructions).toHaveBeenLastCalledWith('')
    expect(textarea.element.value).toBe('')
  })

  it('updates the optional display nickname from the profile panel', async () => {
    const wrapper = mount(SettingsPage, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await flushPromises()

    await wrapper.get('input[placeholder="未设置时显示用户名"]').setValue('小蓝')
    const save = wrapper.findAll('button').find((button) => button.text().trim() === '保存个人资料')
    await save.trigger('click')
    await flushPromises()

    expect(updateProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        nickname: '小蓝',
        email: 'operator@example.com',
      }),
    )
  })

  it('sets the six-digit customer mode exit password from account security', async () => {
    const wrapper = mount(SettingsPage, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await flushPromises()

    const securityTab = wrapper
      .findAll('button')
      .find((button) => button.text().includes('账号安全'))
    await securityTab.trigger('click')

    await wrapper.get('input[placeholder="请输入六位数字"]').setValue('654321')
    await wrapper.get('input[placeholder="再次输入六位数字"]').setValue('654321')
    const save = wrapper
      .findAll('button')
      .find((button) => button.text().trim() === '保存顾客模式密码')
    await save.trigger('click')
    await flushPromises()

    expect(updateCustomerModePassword).toHaveBeenCalledWith('654321')
    expect(wrapper.text()).toContain('已设置专用密码')
  })
})
