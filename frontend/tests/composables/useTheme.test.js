import { beforeEach, describe, expect, it } from 'vitest'
import { initializeTheme, useTheme } from '@/composables/useTheme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    delete document.documentElement.dataset.theme
  })

  it('restores a saved dark theme', () => {
    localStorage.setItem('vp_color_theme', 'dark')
    initializeTheme()

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useTheme().isDark.value).toBe(true)
  })

  it('toggles and persists the selected theme', () => {
    localStorage.setItem('vp_color_theme', 'dark')
    initializeTheme()

    useTheme().toggleTheme()

    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('vp_color_theme')).toBe('light')
  })
})
