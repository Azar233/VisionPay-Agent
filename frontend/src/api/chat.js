import request from '@/utils/request'

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

export function createChatSessionApi(title = '新对话') {
  return request.post('/chat/sessions', { title })
}

export function getChatSessionsApi() {
  return request.get('/chat/sessions')
}

export function getChatSessionApi(sessionUuid) {
  return request.get(`/chat/sessions/${sessionUuid}`)
}

export function deleteChatSessionApi(sessionUuid) {
  return request.delete(`/chat/sessions/${sessionUuid}`)
}
