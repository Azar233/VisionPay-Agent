<template>
  <aside
    v-if="petStore.visible"
    ref="petRoot"
    class="vision-pet"
    data-testid="vision-pet"
    :class="{
      'is-dragging': dragging,
      'has-message': Boolean(petStore.message),
      'is-checkout': petStore.state === 'checkout',
      'is-error': petStore.state === 'error',
    }"
    :style="petPositionStyle"
    role="status"
    aria-live="polite"
    :aria-label="ariaLabel"
    tabindex="0"
    @pointerdown="startDrag"
    @pointermove="movePet"
    @pointerup="endDrag"
    @pointercancel="endDrag"
    @keydown="moveWithKeyboard"
  >
    <Transition name="pet-bubble">
      <div
        v-if="petStore.message"
        ref="petMessage"
        class="pet-message"
        :class="{
          'is-positioned': hasBubblePosition,
          'opens-right': bubblePlacement.horizontal === 'right',
          'opens-below': bubblePlacement.vertical === 'below',
        }"
        :style="bubblePositionStyle"
      >
        <span class="pet-status-dot" aria-hidden="true" />
        <div class="pet-message-content">
          <div class="pet-message-heading">
            <span>{{ petStore.message }}</span>
            <strong v-if="petProgress !== null">{{ petProgress }}%</strong>
          </div>
          <div
            v-if="petProgress !== null"
            class="pet-progress"
            role="progressbar"
            aria-label="任务进度"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuenow="petProgress"
          >
            <span :style="{ width: `${petProgress}%` }" />
          </div>
        </div>
      </div>
    </Transition>

    <div class="pet-stage" aria-hidden="true">
      <div class="pet-shadow" />
      <div class="pet-sprite" :style="spriteStyle" />
    </div>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import petSprites from '@/assets/pet/visionpay-pet-sprites-v4.png'
import workingPetSprites from '@/assets/pet/visionpay-pet-working-v1.png'
import errorPetSprites from '@/assets/pet/visionpay-pet-error-v1.png'
import { useVisionPetStore } from '@/stores/visionPet'
import { VISION_PET_TASK_EVENT } from '@/utils/visionPet'

const STORAGE_KEY = 'vp_vision_pet_position'
const EDGE_GAP = 16
const DEFAULT_WIDTH = 134
const DEFAULT_HEIGHT = 181
const DEFAULT_STAGE_WIDTH = 112
const DEFAULT_STAGE_HEIGHT = 160
const MOBILE_WIDTH = 109
const MOBILE_HEIGHT = 146
const MOBILE_STAGE_WIDTH = 90
const MOBILE_STAGE_HEIGHT = 128
const petStore = useVisionPetStore()
const petRoot = ref(null)
const petMessage = ref(null)
const dragging = ref(false)
const position = ref({ x: 0, y: 0 })
const activeFrame = ref(0)
const bubblePlacement = ref({ horizontal: 'left', vertical: 'above' })
const bubblePosition = ref(null)
const isMobileViewport = ref((globalThis.innerWidth || 0) <= 768)

let dragOffset = { x: 0, y: 0 }
let animationTimer
let messageTimer
let bubbleResizeObserver

const sequences = {
  idle: {
    frames: [0, 1, 0, 2, 3, 0],
    durations: [920, 180, 760, 140, 180, 1080],
  },
  checkout: {
    frames: [0, 1, 1, 2, 3],
    durations: [240, 280, 280, 760, 420],
  },
  working: {
    frames: [0, 1, 2, 1, 3, 1],
    durations: [220, 180, 160, 180, 260, 180],
  },
  error: {
    frames: [0, 1, 2, 3, 2, 1],
    durations: [280, 220, 180, 240, 180, 220],
  },
}

const petScale = computed(() => petStore.sizePercent / 100)
const petLayout = computed(() => {
  const mobile = isMobileViewport.value
  const scale = petScale.value
  return {
    width: (mobile ? MOBILE_WIDTH : DEFAULT_WIDTH) * scale,
    height: (mobile ? MOBILE_HEIGHT : DEFAULT_HEIGHT) * scale,
    stageWidth: (mobile ? MOBILE_STAGE_WIDTH : DEFAULT_STAGE_WIDTH) * scale,
    stageHeight: (mobile ? MOBILE_STAGE_HEIGHT : DEFAULT_STAGE_HEIGHT) * scale,
    bubbleBottom: (mobile ? 132 : 164) * scale,
  }
})

const petPositionStyle = computed(() => ({
  width: `${petLayout.value.width}px`,
  height: `${petLayout.value.height}px`,
  '--pet-stage-width': `${petLayout.value.stageWidth}px`,
  '--pet-stage-height': `${petLayout.value.stageHeight}px`,
  '--pet-bubble-bottom': `${petLayout.value.bubbleBottom}px`,
  transform: `translate3d(${position.value.x}px, ${position.value.y}px, 0)`,
}))

const bubblePositionStyle = computed(() =>
  bubblePosition.value
    ? {
        left: `${bubblePosition.value.x}px`,
        top: `${bubblePosition.value.y}px`,
      }
    : undefined,
)
const hasBubblePosition = computed(() => bubblePosition.value !== null)

// Only dataset background operations provide a numeric progress value.
// Treat missing legacy/HMR state as no progress so normal chat only shows text.
const petProgress = computed(() =>
  petStore.showProgress && Number.isFinite(petStore.progress)
    ? Math.max(0, Math.min(100, Math.round(petStore.progress)))
    : null,
)

const spriteStyle = computed(() => {
  const isWorking = petStore.state === 'working'
  const isError = petStore.state === 'error'
  return {
    backgroundImage: `url(${isError ? errorPetSprites : isWorking ? workingPetSprites : petSprites})`,
    backgroundSize: isWorking || isError ? '400% 100%' : '400% 200%',
    backgroundPosition: `${(activeFrame.value / 3) * 100}% ${petStore.state === 'checkout' ? 100 : 0}%`,
  }
})

const stateLabels = {
  idle: '待机',
  working: '工作',
  checkout: '结算',
  error: '报错',
}

const ariaLabel = computed(() =>
  petStore.message
    ? `Vico：${petStore.message}${petProgress.value !== null ? `，进度 ${petProgress.value}%` : ''}`
    : `Vico，当前为${stateLabels[petStore.state] || stateLabels.idle}状态，可拖动`,
)

function petBounds() {
  const rect = petRoot.value?.getBoundingClientRect()
  return {
    width: rect?.width || petLayout.value.width,
    height: rect?.height || petLayout.value.height,
  }
}

function clampPosition(nextPosition) {
  const { width, height } = petBounds()
  return {
    x: Math.min(
      Math.max(EDGE_GAP, nextPosition.x),
      Math.max(EDGE_GAP, window.innerWidth - width - EDGE_GAP),
    ),
    y: Math.min(
      Math.max(EDGE_GAP, nextPosition.y),
      Math.max(EDGE_GAP, window.innerHeight - height - EDGE_GAP),
    ),
  }
}

function updateBubblePosition() {
  const bubble = petMessage.value
  if (!bubble || !petStore.message) {
    bubblePosition.value = null
    return
  }

  const bubbleWidth = bubble.offsetWidth
  const bubbleHeight = bubble.offsetHeight
  if (!bubbleWidth || !bubbleHeight) return

  const { width: petWidth, height: petHeight } = petBounds()
  const scale = petScale.value
  const sideInset = (isMobileViewport.value ? 4 : 10) * scale
  const aboveBottom = petLayout.value.bubbleBottom
  const belowOverlap = 12 * scale
  const viewportLeft = EDGE_GAP
  const viewportTop = EDGE_GAP
  const viewportRight = window.innerWidth - EDGE_GAP
  const viewportBottom = window.innerHeight - EDGE_GAP

  const leftSpace = position.value.x + petWidth - sideInset - viewportLeft
  const rightSpace = viewportRight - (position.value.x + sideInset)
  const horizontal = rightSpace >= bubbleWidth || rightSpace > leftSpace ? 'right' : 'left'

  const aboveBottomY = position.value.y + petHeight - aboveBottom
  const belowTopY = position.value.y + petHeight - belowOverlap
  const aboveSpace = aboveBottomY - viewportTop
  const belowSpace = viewportBottom - belowTopY
  const vertical = aboveSpace >= bubbleHeight || aboveSpace >= belowSpace ? 'above' : 'below'

  const desiredLeft =
    horizontal === 'right'
      ? position.value.x + sideInset
      : position.value.x + petWidth - sideInset - bubbleWidth
  const desiredTop = vertical === 'below' ? belowTopY : aboveBottomY - bubbleHeight
  const clampedLeft = Math.min(
    Math.max(viewportLeft, desiredLeft),
    Math.max(viewportLeft, viewportRight - bubbleWidth),
  )
  const clampedTop = Math.min(
    Math.max(viewportTop, desiredTop),
    Math.max(viewportTop, viewportBottom - bubbleHeight),
  )

  bubblePlacement.value = { horizontal, vertical }
  bubblePosition.value = {
    x: clampedLeft - position.value.x,
    y: clampedTop - position.value.y,
  }
}

function observeBubbleSize() {
  bubbleResizeObserver?.disconnect()
  if (!petMessage.value || typeof ResizeObserver === 'undefined') return
  bubbleResizeObserver = new ResizeObserver(updateBubblePosition)
  bubbleResizeObserver.observe(petMessage.value)
}

function savePosition() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(position.value))
}

function restorePosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY))
    if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) {
      position.value = clampPosition(saved)
      return
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY)
  }

  const { width, height } = petBounds()
  position.value = clampPosition({
    x: window.innerWidth - width - 28,
    y: window.innerHeight - height - 24,
  })
}

function startDrag(event) {
  if (event.button !== undefined && event.button !== 0) return
  dragging.value = true
  dragOffset = {
    x: event.clientX - position.value.x,
    y: event.clientY - position.value.y,
  }
  petRoot.value?.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}

function movePet(event) {
  if (!dragging.value) return
  position.value = clampPosition({
    x: event.clientX - dragOffset.x,
    y: event.clientY - dragOffset.y,
  })
}

function endDrag(event) {
  if (!dragging.value) return
  dragging.value = false
  const pointerId = event?.pointerId
  if (Number.isFinite(pointerId) && petRoot.value?.hasPointerCapture?.(pointerId)) {
    petRoot.value.releasePointerCapture(pointerId)
  }
  savePosition()
}

function moveWithKeyboard(event) {
  const directions = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }
  const direction = directions[event.key]
  if (!direction) return
  const step = event.shiftKey ? 24 : 8
  position.value = clampPosition({
    x: position.value.x + direction[0] * step,
    y: position.value.y + direction[1] * step,
  })
  savePosition()
  event.preventDefault()
}

function scheduleFrame(frameIndex = 0) {
  window.clearTimeout(animationTimer)
  const sequence = sequences[petStore.state] || sequences.idle
  const normalizedIndex = frameIndex % sequence.frames.length
  activeFrame.value = sequence.frames[normalizedIndex]
  animationTimer = window.setTimeout(
    () => scheduleFrame(normalizedIndex + 1),
    sequence.durations[normalizedIndex],
  )
}

function scheduleMessageDismiss(duration = 4200) {
  window.clearTimeout(messageTimer)
  if (!petStore.message || duration <= 0) return
  messageTimer = window.setTimeout(() => {
    petStore.clearMessage()
    if (petStore.state === 'checkout' || petStore.state === 'error') petStore.setState('idle')
  }, duration)
}

function handleTaskEvent(event) {
  const detail = event.detail || {}
  petStore.notify(detail)
  scheduleMessageDismiss(Number.isFinite(detail.duration) ? detail.duration : 4200)
}

function keepOnScreen() {
  isMobileViewport.value = window.innerWidth <= 768
  position.value = clampPosition(position.value)
  savePosition()
  nextTick(updateBubblePosition)
}

watch(
  () => petStore.state,
  () => scheduleFrame(0),
)
watch(
  () => petStore.sizePercent,
  () => nextTick(keepOnScreen),
)
watch(
  () => petStore.visible,
  (visible) => {
    if (visible) nextTick(keepOnScreen)
  },
)
watch(
  () => petStore.messageId,
  () => {
    nextTick(() => {
      position.value = clampPosition(position.value)
      observeBubbleSize()
      updateBubblePosition()
    })
  },
)
watch([() => position.value.x, () => position.value.y], () => nextTick(updateBubblePosition))

onMounted(async () => {
  await nextTick()
  restorePosition()
  scheduleFrame(0)
  window.addEventListener('resize', keepOnScreen)
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('mouseup', endDrag)
  window.addEventListener('blur', endDrag)
  window.addEventListener(VISION_PET_TASK_EVENT, handleTaskEvent)

  petStore.notify({ state: 'idle', message: 'Vico 已就绪，拖动我试试' })
  scheduleMessageDismiss(3600)
})

onBeforeUnmount(() => {
  window.clearTimeout(animationTimer)
  window.clearTimeout(messageTimer)
  bubbleResizeObserver?.disconnect()
  window.removeEventListener('resize', keepOnScreen)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('mouseup', endDrag)
  window.removeEventListener('blur', endDrag)
  window.removeEventListener(VISION_PET_TASK_EVENT, handleTaskEvent)
})
</script>

<style lang="scss" scoped>
.vision-pet {
  position: fixed;
  z-index: 2100;
  top: 0;
  left: 0;
  width: 134px;
  height: 181px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  will-change: transform;
  outline: none;
  filter: drop-shadow(0 14px 20px rgba(0, 0, 0, 0.12));
}

.vision-pet:focus-visible .pet-stage {
  border-radius: 28px;
  box-shadow: $ring-primary;
}

.vision-pet.is-dragging {
  cursor: grabbing;
  filter: drop-shadow(0 20px 26px rgba(0, 0, 0, 0.2));
}

.pet-stage {
  position: relative;
  width: var(--pet-stage-width, 112px);
  height: var(--pet-stage-height, 160px);
  flex: 0 0 var(--pet-stage-height, 160px);
  transition: transform 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.vision-pet:hover .pet-stage {
  transform: translateY(-3px);
}
.vision-pet.is-dragging .pet-stage {
  transform: scale(1.03) translateY(-5px);
}

.pet-sprite {
  position: absolute;
  inset: 0;
  z-index: 1;
  background-repeat: no-repeat;
  background-size: 400% 200%;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
}

.pet-shadow {
  position: absolute;
  z-index: 0;
  left: 29%;
  right: 29%;
  bottom: 4px;
  height: 9px;
  border-radius: 50%;
  background: rgba(20, 26, 47, 0.14);
  filter: blur(5px);
}

.pet-message {
  position: absolute;
  right: 10px;
  bottom: var(--pet-bubble-bottom, 164px);
  max-width: min(260px, calc(100vw - 32px));
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 13px;
  color: $text-primary;
  background: color-mix(in srgb, var(--vp-surface) 92%, transparent);
  border: 1px solid $border-color;
  border-radius: 14px 14px 4px 14px;
  box-shadow: $shadow-md;
  backdrop-filter: blur(18px) saturate(130%);
  -webkit-backdrop-filter: blur(18px) saturate(130%);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  pointer-events: none;
}

.pet-message.opens-right {
  border-radius: 14px 14px 14px 4px;
}
.pet-message.opens-below {
  border-radius: 4px 14px 14px 14px;
}
.pet-message.opens-right.opens-below {
  border-radius: 14px 4px 14px 14px;
}
.pet-message.is-positioned {
  right: auto;
  bottom: auto;
}

.pet-message-content {
  min-width: min(172px, calc(100vw - 74px));
  max-width: 100%;
}
.pet-message-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.pet-message-heading > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.pet-message-heading strong {
  color: $primary-color;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.pet-progress {
  width: 100%;
  height: 4px;
  margin-top: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--vp-primary) 13%, transparent);
}
.pet-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: $primary-color;
  transition: width 0.24s ease;
}

.pet-status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: $success-color;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--vp-success) 16%, transparent);
}

.vision-pet.is-checkout .pet-message {
  border-color: color-mix(in srgb, var(--vp-success) 42%, var(--vp-border));
}

.vision-pet.is-error .pet-message {
  border-color: color-mix(in srgb, var(--vp-danger) 42%, var(--vp-border));
}

.vision-pet.is-error .pet-status-dot {
  background: $danger-color;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--vp-danger) 16%, transparent);
}

.pet-bubble-enter-active,
.pet-bubble-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.pet-bubble-enter-from,
.pet-bubble-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.98);
}

@media (max-width: 768px) {
  .pet-message {
    right: 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pet-stage {
    transition: none;
  }
}
</style>
