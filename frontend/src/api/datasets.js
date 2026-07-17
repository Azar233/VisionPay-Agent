import request from '@/utils/request'

export function getDatasetVersionsApi(params = {}) {
  return request.get('/datasets', { params })
}

export function getDatasetVersionApi(datasetId) {
  return request.get(`/datasets/${datasetId}`)
}

export function createDatasetVersionApi(data) {
  return request.post('/datasets', data)
}

export function importBaselineDatasetApi(data) {
  return request.post('/datasets/import-baseline', data, { timeout: 0 })
}

export function importAvailableModelApi(formData) {
  return request.post('/datasets/import-available-model', formData, {
    // Let the browser append the multipart boundary for the selected best.pt.
    timeout: 0,
  })
}

export function deriveDatasetVersionApi(datasetId, data) {
  return request.post(`/datasets/${datasetId}/derive`, data, { timeout: 0 })
}

export function deriveDatasetVersionTaskApi(datasetId, data) {
  return request.post(`/datasets/${datasetId}/derive-task`, data, { skipPetError: true })
}

export function stageDatasetProductImagesApi(datasetId, formData) {
  return request.post(`/datasets/${datasetId}/products/stage`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 0,
  })
}

export function commitDatasetProductApi(datasetId, data) {
  return request.post(`/datasets/${datasetId}/products/commit`, data, { timeout: 0 })
}

export function commitDatasetProductTaskApi(datasetId, data) {
  return request.post(`/datasets/${datasetId}/products/commit-task`, data, { skipPetError: true })
}

export function discardDatasetProductStageApi(datasetId, stagingToken) {
  return request.delete(`/datasets/${datasetId}/products/stage/${stagingToken}`)
}

export function deleteDatasetProductApi(datasetId, productId, deactivateProduct = true) {
  return request.delete(`/datasets/${datasetId}/products/${productId}`, {
    data: { deactivate_product: deactivateProduct },
    timeout: 0,
  })
}

export function deleteDatasetProductTaskApi(datasetId, productId, deactivateProduct = true) {
  return request.post(`/datasets/${datasetId}/products/${productId}/delete-task`, {
    deactivate_product: deactivateProduct,
  }, { skipPetError: true })
}

export function updateDatasetVersionApi(datasetId, data) {
  return request.put(`/datasets/${datasetId}`, data)
}

export function validateDatasetVersionApi(datasetId, checkFilesystem = false) {
  return request.post(`/datasets/${datasetId}/validate`, {
    check_filesystem: checkFilesystem,
  })
}

export function freezeDatasetVersionApi(datasetId, checkFilesystem = false) {
  return request.post(`/datasets/${datasetId}/freeze`, {
    check_filesystem: checkFilesystem,
  })
}

export function archiveDatasetVersionApi(datasetId) {
  return request.post(`/datasets/${datasetId}/archive`)
}

export function deleteDatasetVersionApi(datasetId) {
  return request.delete(`/datasets/${datasetId}`)
}

export function deleteDatasetVersionTaskApi(datasetId) {
  return request.post(`/datasets/${datasetId}/delete-task`, undefined, { skipPetError: true })
}

export function getDatasetOperationStatusApi(taskId) {
  return request.get(`/datasets/operations/${taskId}`, { skipGlobalError: true })
}
