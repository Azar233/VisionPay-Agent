import { onBeforeUnmount, ref, unref, watch } from 'vue'

/**
 * 数字滚动动画：target（ref 或 getter）变化时，从当前值平滑滚动到新值。
 * prefers-reduced-motion 下直接落终值。
 *
 * const count = useCountUp(() => stats.total, { duration: 700 })
 * 模板中：{{ Math.round(count.value) }}
 */
export function useCountUp(target, { duration = 700, initial = 0 } = {}) {
  const value = ref(initial)
  let rafId = 0
  let displayed = initial

  const reduceMotion = () =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  function stop() {
    if (rafId) cancelAnimationFrame(rafId)
    rafId = 0
  }

  function animate(to) {
    stop()
    const from = displayed
    if (reduceMotion() || duration <= 0 || from === to) {
      displayed = to
      value.value = to
      return
    }
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      displayed = from + (to - from) * eased
      value.value = displayed
      if (t < 1) rafId = requestAnimationFrame(tick)
      else rafId = 0
    }
    rafId = requestAnimationFrame(tick)
  }

  watch(
    () => unref(typeof target === 'function' ? target() : target),
    (to) => animate(Number(to) || 0),
    { immediate: true },
  )

  onBeforeUnmount(stop)

  return value
}
