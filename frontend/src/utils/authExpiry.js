import { ElMessage } from 'element-plus'
import router from '@/router'

const TOKEN_KEY = 'vp_agent_token'
const USER_KEY = 'vp_agent_user'

let expirationInProgress = false

/**
 * Handle an expired login session once, even when several requests return 401
 * at the same time. The flag is reset after a successful login.
 */
export function handleAuthExpired({ clearSession, redirectPath } = {}) {
  if (expirationInProgress) return false
  expirationInProgress = true

  clearSession?.()
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)

  const currentRoute = router.currentRoute.value
  if (currentRoute.path !== '/welcome' || currentRoute.query?.entry !== 'core') {
    const target = redirectPath || currentRoute.fullPath || '/'
    ElMessage.error('登录已过期，请重新登录')
    router.replace({ path: '/welcome', query: { entry: 'core', redirect: target } })
  }

  return true
}

export function resetAuthExpiryState() {
  expirationInProgress = false
}
