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

export function calculateCheckoutApi(items, modelVersionId = null) {
  return request.post('/checkout/calculate', {
    items: items.map((item) => ({
      class_id: item.classId,
      quantity: item.quantity,
    })),
    model_version_id: modelVersionId,
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
