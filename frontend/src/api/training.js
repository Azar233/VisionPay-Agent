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

export function stopTrainingApi(taskId) {
  return request.post(`/training/stop/${taskId}`)
}

export function downloadTrainingResultsApi(taskUuid) {
  return request.get(`/training/results/${taskUuid}`, {
    responseType: 'blob',
  })
}
