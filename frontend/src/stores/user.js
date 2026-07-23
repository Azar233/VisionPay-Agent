/**
 * 用户状态管理
 * 管理用户登录信息、Token、角色等
 */
import { defineStore } from 'pinia'
import { loginApi, getUserInfoApi } from '@/api/auth'
import { useAgentStore } from '@/stores/agent'
import { useCustomerModeStore } from '@/stores/customerMode'

const TOKEN_KEY = 'vp_agent_token'
const USER_KEY = 'vp_agent_user'

export const useUserStore = defineStore('user', {
  state: () => ({
    // JWT Token
    token: localStorage.getItem(TOKEN_KEY) || '',
    // 用户信息
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
  }),

  getters: {
    /** 是否已登录 */
    isLoggedIn: (state) => !!state.token,
    /** 用户名 */
    username: (state) => state.user?.username || '',
    /** 可重复、可修改的展示昵称 */
    nickname: (state) => state.user?.nickname || '',
    /** 界面展示名称，未设置昵称时回退到用户名 */
    displayName: (state) => state.user?.nickname?.trim() || state.user?.username || '',
    /** 用户头像 */
    avatar: (state) => state.user?.avatar || '',
    /** 用户角色列表 */
    roles: (state) => state.user?.roles || [],
    /** 是否为管理员 */
    isSuperuser: (state) => state.user?.is_superuser || false,
  },

  actions: {
    setUser(user) {
      this.user = user
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    /**
     * 用户登录
     * @param {Object} credentials - { username, password }
     */
    async login(credentials) {
      const res = await loginApi(credentials)
      // 每次新的登录会话都从空白对话开始，不恢复上一个账号或上次登录的活动会话。
      useAgentStore().clear()
      useCustomerModeStore().exit()
      // 保存 Token
      this.token = res.access_token
      localStorage.setItem(TOKEN_KEY, res.access_token)
      // 保存用户信息
      this.setUser(res.user)
      return res
    },

    /**
     * 获取最新用户信息
     */
    async fetchUserInfo() {
      try {
        const user = await getUserInfoApi()
        this.setUser(user)
      } catch {
        this.logout()
      }
    },

    /**
     * 退出登录
     */
    logout() {
      useAgentStore().clear()
      useCustomerModeStore().exit()
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})
