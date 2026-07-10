import request from '@/utils/request'

export function startTrainingApi(data) {
  return request.post('/training/start', data)
}

export function getTrainingTasksApi() {
  return request.get('/training/tasks')
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

export function predictTrainingImageApi(formData) {
  return request.post('/training/predict', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 0,
  })
}
