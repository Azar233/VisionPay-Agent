import router from '@/router'

function expireLogin() {
  localStorage.removeItem('vp_agent_token')
  localStorage.removeItem('vp_agent_user')
  const currentPath = router.currentRoute.value.fullPath
  if (router.currentRoute.value.path !== '/login') {
    router.replace({ path: '/login', query: { redirect: currentPath } })
  }
}

/** Parse a POST-based SSE stream without losing frames split across network chunks. */
export function streamChat(url, body, callbacks = {}) {
  const { onMessage, onDone, onError } = callbacks
  const token = localStorage.getItem('vp_agent_token')
  const controller = new AbortController()

  const completion = fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (response) => {
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
          onMessage?.(JSON.parse(data))
        } catch {
          onMessage?.({ type: 'text_chunk', content: data })
        }
      }
    }
  }).catch((error) => {
    if (error.name !== 'AbortError') onError?.(error)
  })

  return { stop: () => controller.abort(), completion }
}
