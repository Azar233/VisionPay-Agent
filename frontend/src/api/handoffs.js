import request from '@/utils/request'

export function getAgentHandoffApi(handoffId) {
  return request.get(`/agent/handoffs/${handoffId}`)
}

export function updateAgentHandoffApi(handoffId, payload) {
  return request.patch(`/agent/handoffs/${handoffId}`, payload)
}
