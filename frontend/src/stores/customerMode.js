import { defineStore } from 'pinia'
import {
  clearPersistedCustomerMode,
  persistCustomerMode,
  readPersistedCustomerMode,
} from '@/utils/customerMode'

export const useCustomerModeStore = defineStore('customer-mode', {
  state: () => readPersistedCustomerMode(),

  getters: {
    isActiveFor: (state) => (userId) =>
      Boolean(state.enabled && state.ownerUserId && state.ownerUserId === Number(userId)),
  },

  actions: {
    enter(userId) {
      const state = persistCustomerMode(userId)
      this.enabled = state.enabled
      this.ownerUserId = state.ownerUserId
    },
    exit() {
      this.enabled = false
      this.ownerUserId = null
      clearPersistedCustomerMode()
    },
  },
})
