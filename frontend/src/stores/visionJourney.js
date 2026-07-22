import { defineStore } from 'pinia'

const ENTRY_MODES = new Set(['awakening', 'core', 'replay'])

/** 仅管理登录引导的界面状态；认证状态仍完全由原有 user store 管理。 */
export const useVisionJourneyStore = defineStore('vision-journey', {
  state: () => ({
    entryMode: 'awakening',
    currentChapter: 0,
    isPortalActive: false,
  }),

  actions: {
    setEntryMode(mode = 'awakening') {
      this.entryMode = ENTRY_MODES.has(mode) ? mode : 'awakening'
    },
    setCurrentChapter(chapter) {
      this.currentChapter = Math.max(0, Number(chapter) || 0)
    },
    setPortalActive(active) {
      this.isPortalActive = Boolean(active)
    },
    resetRun() {
      this.currentChapter = 0
      this.isPortalActive = false
    },
  },
})
