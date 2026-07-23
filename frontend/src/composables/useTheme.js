import { computed, ref } from 'vue'

const STORAGE_KEY = 'vp_color_theme'
const isDark = ref(false)

function preferredTheme() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  // 深色是品牌主视觉，未表达偏好时默认深色。
  return 'dark'
}

function applyTheme(theme, persist = true) {
  const dark = theme === 'dark'
  isDark.value = dark
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
  if (persist) localStorage.setItem(STORAGE_KEY, theme)
}

export function initializeTheme() {
  applyTheme(preferredTheme(), false)
}

export function useTheme() {
  const themeLabel = computed(() => (isDark.value ? '切换为浅色' : '切换为深色'))
  const currentTheme = computed(() => (isDark.value ? 'dark' : 'light'))

  function toggleTheme() {
    applyTheme(isDark.value ? 'light' : 'dark')
  }

  return { isDark, currentTheme, themeLabel, toggleTheme }
}
