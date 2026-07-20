/**
 * Axios 请求封装
 * - 统一 baseURL 配置
 * - 请求拦截器：自动注入 JWT Token
 * - 响应拦截器：统一错误处理、Token 过期处理
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { handleAuthExpired, resetAuthExpiryState } from '@/utils/authExpiry'
import { getBackendErrorMessage, notifyVisionPetBackendError } from '@/utils/visionPet'

// ── 创建 Axios 实例 ──────────────────────────────────
const request = axios.create({
  baseURL: '/api', // 配合 Vite proxy，实际请求转发到后端
  timeout: 30000, // 请求超时 30 秒
  // 不设置默认 Content-Type，让 Axios 根据请求体自动选择：
  // 普通对象 -> application/json，FormData -> multipart/form-data（浏览器自动加 boundary）
})

// ── 请求拦截器 ──────────────────────────────────────
request.interceptors.request.use(
  (config) => {
    // 从 Pinia store 获取 Token，自动注入请求头
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

// ── 响应拦截器 ──────────────────────────────────────
request.interceptors.response.use(
  (response) => {
    if (response.config?.url?.includes('/auth/login')) resetAuthExpiryState()
    // 请求成功，直接返回响应数据
    return response.data
  },
  (error) => {
    const { response } = error
    const isLoginRequest = error.config?.url?.includes('/auth/login')
    if (response?.status === 401 && !isLoginRequest) {
      handleAuthExpired({ clearSession: () => useUserStore().logout() })
      return Promise.reject(error)
    }
    if (error.config?.skipGlobalError) {
      return Promise.reject(error)
    }
    notifyVisionPetBackendError(error)
    if (response) {
      const detail = getBackendErrorMessage(error, `请求失败 (${response.status})`)
      switch (response.status) {
        case 403:
          ElMessage.error('没有权限执行此操作')
          break
        case 404:
          ElMessage.error(detail || '请求的资源不存在')
          break
        case 422:
          // Pydantic 验证错误
          const validationDetail = response.data?.detail ?? response.data?.data
          if (Array.isArray(validationDetail)) {
            ElMessage.error(validationDetail[0]?.msg || validationDetail[0] || '参数验证失败')
          } else {
            ElMessage.error(validationDetail || detail || '参数验证失败')
          }
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(detail)
      }
    } else {
      // 网络错误或请求超时
      ElMessage.error('网络连接异常，请检查后端服务是否启动')
    }
    return Promise.reject(error)
  },
)

export default request
