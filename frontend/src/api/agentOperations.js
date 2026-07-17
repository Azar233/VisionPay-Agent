import request from '@/utils/request'

export function getAgentOperationApi(operationUuid, config = {}) {
  return request.get(`/agent/operations/${operationUuid}`, config)
}

export function listAgentOperationsApi(params = {}) {
  return request.get('/agent/operations', { params })
}

export function rotateAgentOperationTokenApi(operationUuid, config = {}) {
  return request.post(`/agent/operations/${operationUuid}/token`, undefined, config)
}

export function confirmAgentOperationApi(operationUuid, confirmationToken, idempotencyKey, config = {}) {
  return request.post(`/agent/operations/${operationUuid}/confirm`, {
    confirmation_token: confirmationToken,
    idempotency_key: idempotencyKey,
  }, config)
}

export function cancelAgentOperationApi(operationUuid) {
  return request.post(`/agent/operations/${operationUuid}/cancel`)
}
