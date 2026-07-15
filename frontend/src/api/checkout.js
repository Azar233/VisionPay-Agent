import request from '@/utils/request'

export function detectCheckoutApi(file, options = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('conf', String(options.conf ?? 0.25))
  form.append('iou', String(options.iou ?? 0.45))
  if (options.sceneId) form.append('scene_id', String(options.sceneId))
  return request.post('/checkout/detect', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 0,
  })
}

export function calculateCheckoutApi(items) {
  return request.post('/checkout/calculate', {
    items: items.map((item) => ({
      class_id: item.classId,
      quantity: item.quantity,
    })),
  })
}

export function createMockPaymentOrderApi(items) {
  return request.post('/mock-pay/orders', {
    items: items.map((item) => ({
      class_id: item.classId ?? item.class_id,
      quantity: item.quantity ?? item.count,
    })),
  })
}

export function getMockPaymentStatusApi(orderUuid) {
  return request.get(`/mock-pay/orders/${orderUuid}/status`, { skipGlobalError: true })
}

export function getMockPaymentOrderApi(paymentToken) {
  return request.get(`/mock-pay/${paymentToken}`, { skipGlobalError: true })
}

export function confirmMockPaymentApi(paymentToken, paymentMethod) {
  return request.post(
    `/mock-pay/${paymentToken}/confirm`,
    { payment_method: paymentMethod },
    { skipGlobalError: true },
  )
}

/**
 * 查询订单历史
 * @param {Object} params
 * @param {string} [params.start_date]
 * @param {string} [params.end_date]
 * @param {string} [params.status]
 * @param {number} [params.page]
 * @param {number} [params.page_size]
 */
export function getMockPaymentOrderHistoryApi(params = {}) {
  return request.get('/mock-pay/orders/history', { params })
}

/**
 * 查询订单详情
 * @param {string} orderUuid
 */
export function getMockPaymentOrderDetailApi(orderUuid) {
  return request.get(`/mock-pay/orders/${orderUuid}`)
}

/**
 * 删除订单
 * @param {string} orderUuid
 */
export function deleteMockPaymentOrderApi(orderUuid) {
  return request.delete(`/mock-pay/orders/${orderUuid}`)
}
