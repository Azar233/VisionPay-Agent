import { defineStore } from 'pinia'

const SUPPORTED_STATES = new Set(['idle', 'working', 'checkout', 'error'])
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

export const useVisionPetStore = defineStore('vision-pet', {
  state: () => {
    const preferences = readPreferences()
    return {
      state: 'idle',
      message: '',
      progress: null,
      showProgress: false,
      messageId: 0,
      visible: preferences.visible,
      sizePercent: preferences.sizePercent,
    }
  },

  actions: {
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
      this.state = SUPPORTED_STATES.has(nextState) ? nextState : 'idle'
    },
    notify({ state = 'idle', message = '', progress = null, showProgress = false } = {}) {
      this.setState(state)
      this.message = String(message || '')
      const numericProgress = Number(progress)
      this.progress =
        progress !== null && progress !== '' && Number.isFinite(numericProgress)
          ? Math.max(0, Math.min(100, Math.round(numericProgress)))
          : null
      this.showProgress = Boolean(showProgress)
      this.messageId += 1
    },
    clearMessage() {
      this.message = ''
      this.progress = null
      this.showProgress = false
    },
    reset() {
      this.state = 'idle'
      this.message = ''
      this.progress = null
      this.showProgress = false
    },
  },
})
