export const CUSTOMER_MODE_STORAGE_KEY = 'vp_customer_mode'
const USER_STORAGE_KEY = 'vp_agent_user'
const CUSTOMER_MODE_ALLOWED_PATHS = new Set(['/checkout', '/checkout/payment'])

function parseStoredJson(key) {
  try {
    return JSON.parse(globalThis.localStorage?.getItem(key) || 'null')
  } catch {
    return null
  }
}

export function readPersistedCustomerMode() {
  const stored = parseStoredJson(CUSTOMER_MODE_STORAGE_KEY)
  return {
    enabled: stored?.enabled === true,
    ownerUserId: Number(stored?.ownerUserId) || null,
  }
}

export function persistCustomerMode(ownerUserId) {
  const state = {
    enabled: true,
    ownerUserId: Number(ownerUserId) || null,
  }
  globalThis.localStorage?.setItem(CUSTOMER_MODE_STORAGE_KEY, JSON.stringify(state))
  return state
}

export function clearPersistedCustomerMode() {
  globalThis.localStorage?.removeItem(CUSTOMER_MODE_STORAGE_KEY)
}

export function isPersistedCustomerModeActive() {
  const mode = readPersistedCustomerMode()
  const user = parseStoredJson(USER_STORAGE_KEY)
  return Boolean(mode.enabled && mode.ownerUserId && mode.ownerUserId === Number(user?.id))
}

export function resolveCustomerModeNavigation(
  to,
  token = globalThis.localStorage?.getItem('vp_agent_token'),
  active = isPersistedCustomerModeActive(),
) {
  if (
    !token ||
    !active ||
    to.meta?.customerModeAllowed === true ||
    CUSTOMER_MODE_ALLOWED_PATHS.has(to.path)
  ) {
    return true
  }
  return '/checkout'
}
