import { defineStore } from 'pinia'

const SUPPORTED_STATES = new Set(['idle', 'working', 'checkout'])

export const useVisionPetStore = defineStore('vision-pet', {
  state: () => ({
    state: 'idle',
    message: '',
    messageId: 0,
    visible: true,
  }),

  actions: {
    setState(nextState = 'idle') {
      this.state = SUPPORTED_STATES.has(nextState) ? nextState : 'idle'
    },
    notify({ state = 'idle', message = '' } = {}) {
      this.setState(state)
      this.message = String(message || '')
      this.messageId += 1
    },
    clearMessage() {
      this.message = ''
    },
    reset() {
      this.state = 'idle'
      this.message = ''
      this.visible = true
    },
  },
})
