import request from '@/utils/request'

export function getAgentOperationApi(operationUuid) {
  return request.get(`/agent/operations/${operationUuid}`)
}

export function listAgentOperationsApi(params = {}) {
  return request.get('/agent/operations', { params })
}

export function rotateAgentOperationTokenApi(operationUuid) {
  return request.post(`/agent/operations/${operationUuid}/token`)
}

export function confirmAgentOperationApi(operationUuid, confirmationToken, idempotencyKey) {
  return request.post(`/agent/operations/${operationUuid}/confirm`, {
    confirmation_token: confirmationToken,
    idempotency_key: idempotencyKey,
  })
}

export function cancelAgentOperationApi(operationUuid) {
  return request.post(`/agent/operations/${operationUuid}/cancel`)
}
