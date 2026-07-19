import request from '@/utils/request'

export function startTrainingApi(data) {
  return request.post('/training/start', data)
}

export function getTrainingTasksApi() {
  return request.get('/training/tasks')
}

export function getDetectionModelVersionsApi(sceneId = null) {
  return request.get('/training/model-versions', {
    params: sceneId ? { scene_id: sceneId } : {},
  })
}

export function setDefaultDetectionModelApi(modelVersionId) {
  return request.post(`/training/model-versions/${modelVersionId}/set-default`)
}

export function archiveDetectionModelApi(modelVersionId) {
  return request.post(`/training/model-versions/${modelVersionId}/archive`)
}

export function importTrainingRunApi(data) {
  return request.post('/training/import-run', data, { timeout: 0 })
}

export function importLocalTrainingResultsApi(data) {
  return request.post('/training/import-local-results', data, { timeout: 0 })
}

export function getTrainingStatusApi(taskId) {
  return request.get(`/training/status/${taskId}`)
}

export function getTrainingMetricsApi(taskId) {
  return request.get(`/training/metrics/${taskId}`)
}

export function getTrainingLogApi(taskId, lines = 300) {
  return request.get(`/training/logs/${taskId}`, {
    params: { lines },
  })
}

export function stopTrainingApi(taskId) {
  return request.post(`/training/stop/${taskId}`)
}

export function downloadTrainingResultsApi(taskUuid) {
  return request.get(`/training/results/${taskUuid}`, {
    responseType: 'blob',
  })
}


export function validateTrainingTaskApi(taskId, data) {
  return request.post(`/training/validate/${taskId}`, data, { timeout: 0 })
}

export function exportTrainingModelApi(taskId, data) {
  return request.post(`/training/export/${taskId}`, data, { timeout: 0 })
}

export function downloadTrainingModelApi(taskId) {
  return request.get(`/training/download/${taskId}`, {
    responseType: 'blob',
    timeout: 0,
  })
}
