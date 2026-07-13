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
