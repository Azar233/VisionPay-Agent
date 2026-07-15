import request from '@/utils/request'

/**
 * 获取所有商品价格
 */
export function getPricesApi() {
  return request.get('/prices')
}

/**
 * 获取单个商品价格
 * @param {number} categoryId
 */
export function getPriceApi(categoryId) {
  return request.get(`/prices/${categoryId}`)
}

/**
 * 创建单个商品价格
 * @param {Object} data
 */
export function createPriceApi(data) {
  return request.post('/prices', data)
}

/**
 * 更新单个商品价格
 * @param {number} categoryId
 * @param {Object} data
 */
export function updatePriceApi(categoryId, data) {
  return request.put(`/prices/${categoryId}`, data)
}

/**
 * 删除单个商品价格
 * @param {number} categoryId
 */
export function deletePriceApi(categoryId) {
  return request.delete(`/prices/${categoryId}`)
}
