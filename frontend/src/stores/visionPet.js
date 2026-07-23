import { defineStore } from 'pinia'

const SUPPORTED_STATES = new Set(['idle', 'working', 'checkout', 'error'])
const STATE_PRIORITY = Object.freeze({
  idle: 0,
  working: 1,
  checkout: 2,
  error: 3,
})
export const VISION_PET_PREFERENCES_KEY = 'vp_vision_pet_preferences'
export const VISION_PET_DEFAULT_SIZE = 100
export const VISION_PET_MIN_SIZE = 70
export const VISION_PET_MAX_SIZE = 130

function normalizeSize(value) {
  const size = Number(value)
  if (!Number.isFinite(size)) return VISION_PET_DEFAULT_SIZE
  return Math.min(VISION_PET_MAX_SIZE, Math.max(VISION_PET_MIN_SIZE, Math.round(size / 5) * 5))
}

function readPreferences() {
  try {
    const saved = JSON.parse(globalThis.localStorage?.getItem(VISION_PET_PREFERENCES_KEY) || '{}')
    return {
      visible: saved.visible !== false,
      sizePercent: normalizeSize(saved.sizePercent),
    }
  } catch {
    return { visible: true, sizePercent: VISION_PET_DEFAULT_SIZE }
  }
}

function normalizeState(value, fallback = 'idle') {
  return SUPPORTED_STATES.has(value) ? value : fallback
}

function normalizeProgress(value) {
  const progress = Number(value)
  return value !== null && value !== '' && Number.isFinite(progress)
    ? Math.max(0, Math.min(100, Math.round(progress)))
    : null
}

export const useVisionPetStore = defineStore('vision-pet', {
  state: () => {
    const preferences = readPreferences()
    return {
      state: 'idle',
      notificationState: 'idle',
      message: '',
      progress: null,
      showProgress: false,
      messageId: 0,
      tasks: [],
      visible: preferences.visible,
      sizePercent: preferences.sizePercent,
    }
  },

  actions: {
    syncState() {
      const states = this.tasks.map((task) => normalizeState(task.state, 'working'))
      if (this.message) states.push(normalizeState(this.notificationState))
      this.state = states.reduce(
        (current, candidate) =>
          STATE_PRIORITY[candidate] > STATE_PRIORITY[current] ? candidate : current,
        'idle',
      )
    },
    savePreferences() {
      try {
        globalThis.localStorage?.setItem(
          VISION_PET_PREFERENCES_KEY,
          JSON.stringify({
            visible: this.visible,
            sizePercent: this.sizePercent,
          }),
        )
      } catch {
        // Preference persistence is best-effort; the in-memory setting still applies.
      }
    },
    setVisible(visible) {
      this.visible = Boolean(visible)
      this.savePreferences()
    },
    setSizePercent(sizePercent) {
      this.sizePercent = normalizeSize(sizePercent)
      this.savePreferences()
    },
    resetPreferences() {
      this.visible = true
      this.sizePercent = VISION_PET_DEFAULT_SIZE
      this.savePreferences()
    },
    setState(nextState = 'idle') {
      this.notificationState = normalizeState(nextState)
      this.syncState()
    },
    notify({ state = 'idle', message = '', progress = null, showProgress = false } = {}) {
      this.notificationState = normalizeState(state)
      this.message = String(message || '')
      this.progress = normalizeProgress(progress)
      this.showProgress = Boolean(showProgress)
      this.messageId += 1
      this.syncState()
    },
    startTask({
      id,
      state = 'working',
      message = '正在处理任务',
      progress = null,
      showProgress = false,
    } = {}) {
      const taskId = String(id || '')
      if (!taskId) return
      const task = {
        id: taskId,
        state: normalizeState(state, 'working'),
        message: String(message || '正在处理任务'),
        progress: normalizeProgress(progress),
        showProgress: Boolean(showProgress),
      }
      const index = this.tasks.findIndex((item) => item.id === taskId)
      if (index >= 0) this.tasks.splice(index, 1, task)
      else this.tasks.push(task)
      this.messageId += 1
      this.syncState()
    },
    updateTask(id, update = {}) {
      const task = this.tasks.find((item) => item.id === String(id || ''))
      if (!task) return
      if (update.state !== undefined) task.state = normalizeState(update.state, task.state)
      if (update.message !== undefined && update.message !== '') {
        task.message = String(update.message)
      }
      if (update.progress !== undefined) task.progress = normalizeProgress(update.progress)
      if (update.showProgress !== undefined) task.showProgress = Boolean(update.showProgress)
      this.messageId += 1
      this.syncState()
    },
    finishTask(id) {
      const taskId = String(id || '')
      const nextTasks = this.tasks.filter((item) => item.id !== taskId)
      if (nextTasks.length === this.tasks.length) return
      this.tasks = nextTasks
      this.messageId += 1
      this.syncState()
    },
    clearMessage() {
      this.message = ''
      this.progress = null
      this.showProgress = false
      this.notificationState = 'idle'
      this.messageId += 1
      this.syncState()
    },
    reset() {
      this.state = 'idle'
      this.notificationState = 'idle'
      this.message = ''
      this.progress = null
      this.showProgress = false
      this.tasks = []
      this.messageId += 1
    },
  },
})
