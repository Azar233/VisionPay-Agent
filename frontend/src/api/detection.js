import request from '@/utils/request'

function detectionForm(files, options = {}, fieldName = 'file') {
  const form = new FormData()
  files.forEach((file) => form.append(fieldName, file))
  form.append('conf', String(options.conf ?? 0.25))
  form.append('iou', String(options.iou ?? 0.45))
  if (options.sceneId) form.append('scene_id', String(options.sceneId))
  return form
}

export function detectSingleApi(file, options) {
  return request.post('/detection/single', detectionForm([file], options), {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 0,
  })
}

export function detectBatchApi(files, options) {
  return request.post('/detection/batch', detectionForm(files, options, 'files'), {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 0,
  })
}

export function detectZipApi(file, options) {
  return request.post('/detection/zip', detectionForm([file], options), {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 0,
  })
}

export function detectVideoApi(file, options = {}) {
  const form = detectionForm([file], options)
  if (options.frameSampleRate) form.append('frame_sample_rate', String(options.frameSampleRate))
  if (options.maxFrames) form.append('max_frames', String(options.maxFrames))
  return request.post('/detection/video', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

export function getVideoStatusApi(taskId) {
  return request.get(`/detection/video/status/${taskId}`)
}

export function uploadChatFilesApi(files) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return request.post('/chat/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getAgentStatusApi() {
  return request.get('/chat/status')
}

export function createDetectionSessionApi(title = '新对话') {
  return request.post('/chat/sessions', { title })
}

export function getDetectionSessionsApi() {
  return request.get('/chat/sessions')
}

export function getDetectionSessionApi(sessionUuid) {
  return request.get(`/chat/sessions/${sessionUuid}`)
}

export function deleteDetectionSessionApi(sessionUuid) {
  return request.delete(`/chat/sessions/${sessionUuid}`)
}

export function saveDetectionExchangeApi(sessionUuid, data) {
  return request.post(`/chat/sessions/${sessionUuid}/exchanges`, data)
}
