import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export function useNarrativeDriver() {
  const isTouchPrimary = ref(false)
  const prefersReducedMotion = ref(false)

  const initializeNarrativeDriver = () => {
    isTouchPrimary.value = window.matchMedia('(hover: none) and (pointer: coarse)').matches
    prefersReducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  onMounted(() => {
    initializeNarrativeDriver()
    window.addEventListener('resize', initializeNarrativeDriver, { passive: true })
  })
  onBeforeUnmount(() => window.removeEventListener('resize', initializeNarrativeDriver))

  return {
    isTouchPrimary,
    prefersReducedMotion,
    usesScrollDriver: computed(() => !isTouchPrimary.value && !prefersReducedMotion.value),
    initializeNarrativeDriver,
  }
}
