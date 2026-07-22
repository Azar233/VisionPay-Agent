import { onBeforeUnmount, onMounted } from 'vue'
import Lenis from 'lenis'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

/** 第一章快速响应，识别与团队章节保留更充足的展示区间。 */
export const JOURNEY_CHAPTER_RANGES = Object.freeze([
  { start: 0, end: 0.18 },
  { start: 0.18, end: 0.56 },
  { start: 0.56, end: 1 },
])

export function resolveJourneyProgress(progress, chapterCount = JOURNEY_CHAPTER_RANGES.length) {
  const normalizedProgress = gsap.utils.clamp(0, 1, Number(progress) || 0)
  const ranges = JOURNEY_CHAPTER_RANGES.slice(0, Math.max(1, chapterCount))
  let chapterIndex = ranges.findIndex(
    (range, index) => normalizedProgress < range.end || index === ranges.length - 1,
  )
  if (chapterIndex < 0) chapterIndex = ranges.length - 1

  const range = ranges[chapterIndex]
  const rangeLength = Math.max(0.001, range.end - range.start)
  const chapterProgress = gsap.utils.clamp(0, 1, (normalizedProgress - range.start) / rangeLength)

  return { chapterIndex, chapterProgress, progress: normalizedProgress }
}

/** 桌面端 GSAP + Lenis 滚动驱动；触屏与减少动态效果模式继续使用原有降级方案。 */
export function useScrollDriver(rootRef, { chapterCount, onChapterChange, onProgress } = {}) {
  let lenis
  let frameId
  let context

  onMounted(() => {
    const root = rootRef.value
    if (
      !root ||
      root.dataset.entry === 'core' ||
      window.matchMedia('(hover: none) and (pointer: coarse)').matches ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return
    }

    // 比 frontendnew 原始的 0.09 更紧跟滚轮，同时保留惯性与轨迹平滑。
    lenis = new Lenis({
      smoothWheel: true,
      lerp: 0.14,
      wheelMultiplier: 0.95,
      syncTouch: false,
    })
    const raf = (time) => {
      lenis?.raf(time)
      frameId = window.requestAnimationFrame(raf)
    }
    frameId = window.requestAnimationFrame(raf)
    lenis.on('scroll', ScrollTrigger.update)

    context = gsap.context(() => {
      ScrollTrigger.create({
        trigger: root,
        start: 'top top',
        end: 'bottom bottom',
        invalidateOnRefresh: true,
        onUpdate: (self) => {
          const state = resolveJourneyProgress(self.progress, chapterCount)
          onChapterChange?.(state.chapterIndex)
          onProgress?.(state.progress, state)
          gsap.set(root, {
            '--journey-scroll-progress': state.progress,
            '--journey-chapter-progress': state.chapterProgress,
          })
        },
      })
    }, root)

    ScrollTrigger.refresh()
  })

  onBeforeUnmount(() => {
    if (frameId) window.cancelAnimationFrame(frameId)
    context?.revert()
    lenis?.destroy()
  })
}
