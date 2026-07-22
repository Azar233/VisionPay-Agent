<template>
  <main
    ref="journeyRoot"
    class="vision-journey"
    :data-entry="entryMode"
    :style="{
      '--journey-progress': scrollProgress,
      '--login-reveal': loginRevealProgress,
      '--projection-reveal': projectionRevealProgress,
    }"
  >
    <div class="vision-journey__stage">
      <div class="vision-journey__stars" aria-hidden="true"></div>
      <header class="vision-journey__header">
        <span>VISIONPAY</span><small>{{ entryLabel }}</small>
      </header>
      <button
        type="button"
        class="vision-journey__theme-toggle"
        :aria-label="themeLabel"
        @click="toggleTheme"
      >
        <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
        {{ isDark ? '浅色' : '深色' }}
      </button>

      <nav
        v-if="usesScrollDriver"
        class="vision-journey__progress"
        aria-label="Vision Journey progress"
      >
        <button
          v-for="(_, index) in chapters"
          :key="index"
          type="button"
          :class="{ active: currentChapter === index }"
          :aria-label="`前往第 ${index + 1} 章`"
          @click="scrollToChapter(index)"
        >
          <i></i>
        </button>
      </nav>

      <Transition name="chapter" mode="out-in">
        <component
          :is="activeChapter"
          v-if="!prefersReducedMotion"
          :key="currentChapter"
          class="vision-journey__chapter"
          :progress="chapterProgress"
          :ready="entryMode === 'core' || chapterProgress >= 0.72"
          :style="{ '--chapter-progress': chapterProgress }"
        />
      </Transition>

      <ReducedMotionStorySequence v-if="prefersReducedMotion" class="vision-journey__chapter" />
      <HoloLoginPanel
        v-if="prefersReducedMotion"
        class="vision-journey__reduced-login"
        :authenticated="isAuthenticated"
        projection-anchor="vision-character"
        @authenticated="handleAuthenticated"
        @return-workspace="enterWorkspace"
      />
      <div v-else ref="projectionZone" class="vision-journey__character-zone">
        <VisionCharacter
          ref="visionCharacter"
          :pose="vision.pose.value"
          :progress="scrollProgress"
          :login-progress="loginRevealProgress"
        />
        <HoloLoginPanel
          v-if="isFinalChapter"
          ref="holoLoginPanel"
          :class="{ 'is-interactive': loginRevealProgress >= 0.94 }"
          :inert="loginRevealProgress < 0.94"
          :aria-hidden="loginRevealProgress < 0.94"
          :authenticated="isAuthenticated"
          projection-anchor="vision-character"
          @authenticated="handleAuthenticated"
          @return-workspace="enterWorkspace"
        />
      </div>

      <nav
        v-if="isTouchPrimary && !prefersReducedMotion"
        class="vision-journey__touch-nav"
        aria-label="Journey chapters"
      >
        <el-button text :disabled="currentChapter === 0" @click="setChapter(currentChapter - 1)">
          上一步
        </el-button>
        <span>{{ currentChapter + 1 }} / {{ chapters.length }}</span>
        <el-button
          type="primary"
          :disabled="currentChapter === chapters.length - 1"
          @click="setChapter(currentChapter + 1)"
        >
          下一步
        </el-button>
      </nav>

      <SkipIntroControl
        v-if="entryMode === 'awakening' && currentChapter < chapters.length - 1"
        @skip="skipToCore"
      />
      <p v-if="usesScrollDriver && entryMode === 'awakening'" class="vision-journey__scroll-hint">
        向下滚动，展开 Vision Journey
      </p>
    </div>
    <PortalTransition :active="journeyStore.isPortalActive" @complete="finishPortal" />
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useVisionJourneyStore } from '@/stores/visionJourney'
import { useVisionState } from '@/composables/useVisionState'
import { useNarrativeDriver } from '@/composables/useNarrativeDriver'
import { JOURNEY_CHAPTER_RANGES, useScrollDriver } from '@/composables/useScrollDriver'
import { useTheme } from '@/composables/useTheme'
import VisionCharacter from '@/components/vision-experience/VisionCharacter.vue'
import HoloLoginPanel from '@/components/vision-experience/HoloLoginPanel.vue'
import PortalTransition from '@/components/vision-experience/PortalTransition.vue'
import SkipIntroControl from '@/components/vision-experience/SkipIntroControl.vue'
import ChapterAwakening from '@/components/vision-experience/chapters/ChapterAwakening.vue'
import ChapterRecognition from '@/components/vision-experience/chapters/ChapterRecognition.vue'
import ChapterTeam from '@/components/vision-experience/chapters/ChapterTeam.vue'
import ReducedMotionStorySequence from '@/components/vision-experience/ReducedMotionStorySequence.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const journeyStore = useVisionJourneyStore()
const journeyRoot = ref(null)
const projectionZone = ref(null)
const visionCharacter = ref(null)
const holoLoginPanel = ref(null)
const vision = useVisionState()
const { isTouchPrimary, prefersReducedMotion, usesScrollDriver, initializeNarrativeDriver } =
  useNarrativeDriver()
const { isDark, themeLabel, toggleTheme } = useTheme()
const chapters = [ChapterAwakening, ChapterRecognition, ChapterTeam]
const poseByChapter = ['awakening', 'recognition', 'team']
const scrollProgress = ref(0)
const scrollChapterProgress = ref(0)
const loginRedirect = ref('/')
let projectionSyncFrame = 0

const entryMode = computed(() =>
  ['awakening', 'core', 'replay'].includes(route.query.entry) ? route.query.entry : 'awakening',
)
const currentChapter = computed(() => journeyStore.currentChapter)
const activeChapter = computed(() => chapters[currentChapter.value])
const isAuthenticated = computed(() => userStore.isLoggedIn)
const chapterProgress = computed(() => {
  if (entryMode.value === 'core' || isTouchPrimary.value) return 1
  return scrollChapterProgress.value
})
const isFinalChapter = computed(() => currentChapter.value === chapters.length - 1)
const loginRevealProgress = computed(() => {
  if (!isFinalChapter.value) return 0
  if (entryMode.value === 'core' || isTouchPrimary.value) return 1

  return Math.min(1, Math.max(0, (chapterProgress.value - 0.32) / 0.56))
})
const projectionRevealProgress = computed(() => {
  const progress = loginRevealProgress.value
  return progress * progress * (3 - 2 * progress)
})
const isProjectionSettled = computed(() => loginRevealProgress.value >= 0.98)
const entryLabel = computed(
  () => ({ awakening: 'AWAKENING', core: 'VISION CORE', replay: 'REPLAY MODE' })[entryMode.value],
)

function setChapter(index) {
  const nextIndex = Math.min(chapters.length - 1, Math.max(0, Number(index) || 0))
  journeyStore.setCurrentChapter(nextIndex)
  vision.setPose(poseByChapter[nextIndex])
}

function syncProjectionBeam() {
  projectionSyncFrame = 0
  const zone = projectionZone.value
  if (!isProjectionSettled.value) {
    zone?.style.removeProperty('--holo-beam-top')
    return
  }

  const characterElement = visionCharacter.value?.$el
  const panelElement = holoLoginPanel.value?.$el
  const mascotElement = characterElement?.querySelector('.vision-character__mascot')
  if (!zone || !panelElement || !mascotElement) return

  const mascotRect = mascotElement.getBoundingClientRect()
  const panelRect = panelElement.getBoundingClientRect()
  const panelTransform = new DOMMatrixReadOnly(getComputedStyle(panelElement).transform)
  const panelScale = Math.max(0.01, Math.abs(panelTransform.a) || 1)
  const beamTop = Math.min(-4, (mascotRect.bottom - 4 - panelRect.top) / panelScale)

  zone.style.setProperty('--holo-beam-top', `${beamTop}px`)
}

function scheduleProjectionSync() {
  if (projectionSyncFrame) window.cancelAnimationFrame(projectionSyncFrame)
  projectionSyncFrame = window.requestAnimationFrame(syncProjectionBeam)
}

useScrollDriver(journeyRoot, {
  chapterCount: chapters.length,
  onChapterChange: (index) => {
    if (entryMode.value !== 'core') setChapter(index)
  },
  onProgress: (progress, state) => {
    if (entryMode.value !== 'core') {
      scrollProgress.value = progress
      scrollChapterProgress.value = state.chapterProgress
    }
  },
})

function scrollToChapter(index) {
  const rootTop = journeyRoot.value?.getBoundingClientRect().top || 0
  const rootHeight = journeyRoot.value?.offsetHeight || 0
  const scrollRange = Math.max(1, rootHeight - window.innerHeight)
  const range = JOURNEY_CHAPTER_RANGES[index] || JOURNEY_CHAPTER_RANGES[0]
  const rangeTarget = index === 0 ? 0 : Math.min(range.end, range.start + 0.02)
  const target = window.scrollY + rootTop + scrollRange * rangeTarget
  window.scrollTo({ top: target, behavior: 'smooth' })
}

function configureEntry() {
  journeyStore.setEntryMode(entryMode.value)
  journeyStore.resetRun()
  scrollProgress.value = entryMode.value === 'core' ? 1 : 0
  scrollChapterProgress.value = entryMode.value === 'core' ? 1 : 0
  setChapter(entryMode.value === 'core' ? chapters.length - 1 : 0)
}

function skipToCore() {
  router.replace({ query: { ...route.query, entry: 'core' } })
}

function handleAuthenticated(context) {
  loginRedirect.value = context?.redirect || '/'
  vision.setPose('happy')
  journeyStore.setPortalActive(true)
}

function enterWorkspace() {
  loginRedirect.value = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  vision.setPose('happy')
  journeyStore.setPortalActive(true)
}

function finishPortal() {
  journeyStore.setPortalActive(false)
  router.push(loginRedirect.value)
}

onMounted(() => {
  initializeNarrativeDriver()
  configureEntry()
  window.addEventListener('resize', scheduleProjectionSync)
  scheduleProjectionSync()
})

watch(() => route.query.entry, configureEntry)
watch([isProjectionSettled, isFinalChapter], scheduleProjectionSync, { flush: 'post' })

onBeforeUnmount(() => {
  window.removeEventListener('resize', scheduleProjectionSync)
  if (projectionSyncFrame) window.cancelAnimationFrame(projectionSyncFrame)
})
</script>

<style lang="scss" scoped>
.vision-journey {
  min-height: 220vh;
  color: $text-primary;
  background: $vj-bg;
  background-attachment: fixed;
  background-repeat: no-repeat;
  transition: background 0.3s ease;
}
.vision-journey__stage {
  position: sticky;
  top: 0;
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(340px, 1.1fr);
  align-items: center;
  gap: 5vw;
  min-height: 100vh;
  padding: 56px max(28px, calc((100vw - 1240px) / 2));
  overflow: hidden;
}
.vision-journey__stars {
  position: absolute;
  inset: -8%;
  opacity: $vj-star-opacity;
  background-image:
    radial-gradient(circle at 18% 22%, $vj-star-1 0 1px, transparent 1.5px),
    radial-gradient(circle at 71% 17%, $vj-star-2 0 1px, transparent 1.5px),
    radial-gradient(circle at 87% 68%, $vj-star-3 0 1px, transparent 1.5px),
    radial-gradient(circle at 35% 62%, $vj-star-3 0 1px, transparent 1.5px),
    radial-gradient(circle at 58% 85%, $vj-star-1 0 1px, transparent 1.5px),
    radial-gradient(circle at 8% 78%, $vj-star-2 0 1px, transparent 1.5px),
    radial-gradient(circle at 95% 40%, $vj-star-1 0 1px, transparent 1.5px),
    radial-gradient(circle at 45% 8%, $vj-star-2 0 1px, transparent 1.5px);
  background-size:
    210px 190px,
    290px 250px,
    180px 225px,
    150px 170px,
    240px 200px,
    130px 160px,
    260px 230px,
    170px 150px;
  transform: translateY(calc(var(--journey-progress) * -52px))
    scale(calc(1 + var(--journey-progress) * 0.08));
  will-change: transform;
  pointer-events: none;
}
.vision-journey__header {
  position: absolute;
  z-index: 4;
  top: 26px;
  right: max(28px, calc((100vw - 1240px) / 2));
  left: max(28px, calc((100vw - 1240px) / 2));
  display: flex;
  justify-content: space-between;
  color: $vj-header-text;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
}
.vision-journey__header small {
  color: $vj-header-accent;
}
.vision-journey__chapter,
.vision-journey__character-zone {
  position: relative;
  z-index: 1;
}
.vision-journey__character-zone {
  --holo-beam-top: clamp(-96px, calc(-44px - (100vh - 720px) * 0.12), -44px);
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  min-height: min(860px, calc(100vh - 112px));
}
.vision-journey__character-zone :deep(.holo-login) {
  position: absolute;
  top: calc(50% - 82px);
  left: 50%;
  width: min(100%, 410px);
  padding-top: 72px;
  opacity: var(--projection-reveal);
  pointer-events: none;
  transform: translate(-50%, calc((1 - var(--projection-reveal)) * 36px))
    scale(calc(0.96 + var(--projection-reveal) * 0.04));
  transform-origin: center top;
  will-change: opacity, transform;
}
.vision-journey__character-zone :deep(.holo-login.is-interactive) {
  pointer-events: auto;
}
.vision-journey__character-zone :deep(.holo-login__beam) {
  top: var(--holo-beam-top);
  height: calc(72px - var(--holo-beam-top));
  transition:
    top 180ms var(--vp-ease-vision-out),
    height 180ms var(--vp-ease-vision-out);
}
.vision-journey__scroll-hint {
  position: fixed;
  z-index: 4;
  bottom: 26px;
  left: 50%;
  margin: 0;
  color: $vj-scroll-hint;
  font-size: 11px;
  letter-spacing: 0.08em;
  transform: translateX(-50%);
}
.vision-journey__theme-toggle {
  position: fixed;
  z-index: 6;
  top: 60px;
  left: max(28px, calc((100vw - 1240px) / 2));
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid color-mix(in srgb, $agent-detection 35%, $border-color);
  border-radius: 999px;
  color: $text-secondary;
  background: color-mix(in srgb, $surface-color 78%, transparent);
  font-size: 11px;
  letter-spacing: 0.04em;
  cursor: pointer;
  backdrop-filter: blur(14px);
}
.vision-journey__theme-toggle:hover {
  color: $agent-detection;
}
.vision-journey__progress {
  position: fixed;
  z-index: 5;
  top: 50%;
  right: max(22px, calc((100vw - 1320px) / 2));
  display: grid;
  gap: 10px;
  transform: translateY(-50%);
}
.vision-journey__progress button {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2px;
  border: 0;
  color: $vj-progress-text;
  background: transparent;
  cursor: pointer;
}
.vision-journey__progress i {
  width: 7px;
  height: 7px;
  border: 1px solid currentColor;
  border-radius: 50%;
}
.vision-journey__progress button:hover,
.vision-journey__progress button.active {
  color: $vj-progress-text-active;
}
.vision-journey__progress button.active i {
  border-color: $agent-detection;
  background: $agent-detection;
  box-shadow: 0 0 12px $agent-detection;
}
.vision-journey__touch-nav {
  position: fixed;
  z-index: 5;
  right: 16px;
  bottom: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 8px;
  border: 1px solid $vj-nav-border;
  border-radius: 16px;
  background: $vj-nav-bg;
  backdrop-filter: blur(16px);
}
.vision-journey__touch-nav span {
  color: $vj-nav-text;
  font-size: 11px;
}
.chapter-enter-active,
.chapter-leave-active {
  transition:
    opacity var(--vp-motion-base) var(--vp-ease-vision-out),
    transform var(--vp-motion-base) var(--vp-ease-vision-out);
}
.chapter-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.chapter-leave-to {
  opacity: 0;
  transform: translateY(-14px);
}
.vision-journey[data-entry='core'] {
  min-height: 100vh;
}
.vision-journey__reduced-login {
  position: relative;
  z-index: 2;
  align-self: center;
  justify-self: center;
}
.vision-journey__reduced-login :deep(.holo-login) {
  padding-top: 0;
}
.vision-journey__reduced-login :deep(.holo-login__beam) {
  display: none;
}
@media (max-width: 980px) {
  .vision-journey__progress {
    display: none;
  }
}
@media (max-width: 760px) {
  .vision-journey {
    min-height: 100vh;
  }
  .vision-journey__stage {
    grid-template-columns: 1fr;
    align-content: center;
    gap: 10px;
    padding: 70px 24px 90px;
  }
  .vision-journey__chapter {
    order: 2;
    text-align: center;
  }
  .vision-journey__character-zone {
    --holo-beam-top: clamp(-180px, calc(-136px - (100vh - 720px) * 0.08), -136px);
    order: 1;
    min-height: calc(100vh - 160px);
  }
  .vision-journey__chapter :deep(.chapter p) {
    margin-inline: auto;
  }
  .vision-journey__scroll-hint {
    display: none;
  }
  .vision-journey__theme-toggle {
    top: 58px;
    left: 16px;
    padding: 6px 10px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .vision-journey {
    min-height: 100vh;
  }
  .vision-journey__stars {
    opacity: 0.22;
  }
  .vision-journey__stars,
  .vision-journey__character-zone {
    transform: none;
    transition: none;
  }
}
</style>
