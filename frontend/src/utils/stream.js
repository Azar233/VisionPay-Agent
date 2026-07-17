import { getActivePinia } from 'pinia'
import router from '@/router'
import { useAgentStore } from '@/stores/agent'
import { beginVisionPetTask, updateVisionPetTaskFromWorkflow } from '@/utils/visionPet'

function expireLogin() {
  const pinia = getActivePinia()
  if (pinia) useAgentStore(pinia).clear()
  localStorage.removeItem('vp_agent_token')
  localStorage.removeItem('vp_agent_user')
  const currentPath = router.currentRoute.value.fullPath
  if (router.currentRoute.value.path !== '/login') {
    router.replace({ path: '/login', query: { redirect: currentPath } })
  }
}

/** Parse a POST-based SSE stream without losing frames split across network chunks. */
export function streamChat(url, body, callbacks = {}) {
  const {
    onMessage,
    onDone,
    onError,
    trackPet = true,
    petMessage = 'Agent 正在处理任务',
    petDoneMessage = '回答完成',
    petErrorMessage = '任务处理失败',
    petStoppedMessage = '任务已停止',
    petResultDuration = 3200,
  } = callbacks
  const token = localStorage.getItem('vp_agent_token')
  const controller = new AbortController()
  const petTask = trackPet ? beginVisionPetTask({ message: petMessage }) : null
  let replyStarted = false
  let petResult = { message: petDoneMessage, duration: petResultDuration }

  const completion = Promise.resolve().then(() => fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })).then(async (response) => {
    if (response.status === 401) {
      expireLogin()
      throw new Error('登录已过期，请重新登录')
    }
    if (!response.ok) {
      let detail = `请求失败 (${response.status})`
      try {
        const payload = await response.json()
        detail = payload.detail || detail
      } catch {
        // Keep the HTTP fallback when the response is not JSON.
      }
      throw new Error(detail)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let completed = false
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (!completed) onDone?.()
        return
      }
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const data = frame.split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (!data) continue
        if (data === '[DONE]') {
          completed = true
          onDone?.()
          return
        }
        try {
          const event = JSON.parse(data)
          if (event.type === 'error') {
            petResult = { message: petErrorMessage, duration: petResultDuration }
          }
          if (event.type !== 'text_chunk' || !replyStarted) {
            updateVisionPetTaskFromWorkflow(petTask, event)
          }
          if (event.type === 'text_chunk') replyStarted = true
          onMessage?.(event)
        } catch {
          const event = { type: 'text_chunk', content: data }
          if (!replyStarted) updateVisionPetTaskFromWorkflow(petTask, event)
          replyStarted = true
          onMessage?.(event)
        }
      }
    }
  }).catch((error) => {
    if (error.name === 'AbortError') {
      petResult = { message: petStoppedMessage, duration: petResultDuration }
      return
    }
    petResult = { message: petErrorMessage, duration: petResultDuration }
    onError?.(error)
  }).finally(() => petTask?.finish(petResult))

  return { stop: () => controller.abort(), completion }
}
