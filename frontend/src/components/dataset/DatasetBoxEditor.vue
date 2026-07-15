<template>
  <div class="box-editor">
    <div class="editor-toolbar">
      <span>拖动空白处绘制新框；拖动框或四角可调整位置。</span>
      <div>
        <el-button size="small" :disabled="selectedIndex < 0" @click="removeSelected">删除选中框</el-button>
        <el-button size="small" :disabled="!boxes.length" @click="clearBoxes">清空重画</el-button>
      </div>
    </div>

    <div class="canvas-shell">
      <svg
        ref="svgRef"
        class="annotation-canvas"
        :viewBox="`0 0 ${imageWidth} ${imageHeight}`"
        role="img"
        aria-label="商品检测框编辑器"
        @pointermove="continueDrag"
        @pointerup="finishDrag"
        @pointercancel="finishDrag"
      >
        <image :href="imageUrl" x="0" y="0" :width="imageWidth" :height="imageHeight" />
        <rect class="draw-surface" x="0" y="0" :width="imageWidth" :height="imageHeight" @pointerdown="startDraw" />
        <g v-for="(box, index) in boxes" :key="index" class="box-layer">
          <rect
            class="annotation-box"
            :class="{ selected: index === selectedIndex }"
            :x="box.x1"
            :y="box.y1"
            :width="box.x2 - box.x1"
            :height="box.y2 - box.y1"
            @pointerdown.stop="startMove($event, index)"
          />
          <g v-if="index === selectedIndex">
            <circle
              v-for="handle in handles(box)"
              :key="handle.position"
              class="resize-handle"
              :cx="handle.x"
              :cy="handle.y"
              :r="handleRadius"
              @pointerdown.stop="startResize($event, index, handle.position)"
            />
          </g>
          <g class="box-label" :transform="`translate(${box.x1} ${Math.max(labelHeight, box.y1)})`">
            <rect :x="0" :y="-labelHeight" :width="labelWidth(index, box)" :height="labelHeight" rx="3" />
            <text :x="labelHeight * 0.28" :y="-labelHeight * 0.28" :font-size="labelHeight * 0.55">{{ boxLabel(index, box) }}</text>
          </g>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  imageUrl: { type: String, required: true },
  imageWidth: { type: Number, required: true },
  imageHeight: { type: Number, required: true },
  productOptions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'change'])
const svgRef = ref(null)
const selectedIndex = ref(-1)
const dragState = ref(null)
const boxes = computed(() => props.modelValue)
const handleRadius = computed(() => Math.max(5, Math.min(props.imageWidth, props.imageHeight) * 0.012))
const labelHeight = computed(() => Math.max(18, Math.min(props.imageWidth, props.imageHeight) * 0.045))

function productName(productId) {
  const product = props.productOptions.find((item) => Number(item.product_id) === Number(productId))
  return product?.display_name || product?.class_name || ''
}
function boxLabel(index, box) { return productName(box.product_id) || `目标 ${index + 1}` }
function labelWidth(index, box) { return Math.max(labelHeight.value * 3.2, boxLabel(index, box).length * labelHeight.value * 0.72) }
function cloneBoxes() { return boxes.value.map((item) => ({ ...item })) }
function updateBoxes(next) { emit('update:modelValue', next) }
function point(event) {
  const svg = svgRef.value
  const cursor = svg.createSVGPoint()
  cursor.x = event.clientX
  cursor.y = event.clientY
  const transformed = cursor.matrixTransform(svg.getScreenCTM().inverse())
  return {
    x: Math.max(0, Math.min(props.imageWidth, transformed.x)),
    y: Math.max(0, Math.min(props.imageHeight, transformed.y)),
  }
}
function capture(event) { svgRef.value?.setPointerCapture?.(event.pointerId) }
function startDraw(event) {
  const start = point(event)
  const next = cloneBoxes()
  next.push({ x1: start.x, y1: start.y, x2: start.x, y2: start.y, product_id: null })
  selectedIndex.value = next.length - 1
  dragState.value = { type: 'draw', index: selectedIndex.value, start }
  updateBoxes(next)
  capture(event)
}
function startMove(event, index) {
  selectedIndex.value = index
  dragState.value = { type: 'move', index, start: point(event), original: { ...boxes.value[index] } }
  capture(event)
}
function startResize(event, index, position) {
  selectedIndex.value = index
  dragState.value = { type: 'resize', index, position, original: { ...boxes.value[index] } }
  capture(event)
}
function continueDrag(event) {
  const state = dragState.value
  if (!state) return
  const current = point(event)
  const next = cloneBoxes()
  const minimum = 2
  if (state.type === 'draw') {
    next[state.index] = {
      ...next[state.index],
      x1: Math.min(state.start.x, current.x), y1: Math.min(state.start.y, current.y),
      x2: Math.max(state.start.x, current.x), y2: Math.max(state.start.y, current.y),
    }
  } else if (state.type === 'move') {
    const width = state.original.x2 - state.original.x1
    const height = state.original.y2 - state.original.y1
    const x1 = Math.max(0, Math.min(props.imageWidth - width, state.original.x1 + current.x - state.start.x))
    const y1 = Math.max(0, Math.min(props.imageHeight - height, state.original.y1 + current.y - state.start.y))
    next[state.index] = { ...state.original, x1, y1, x2: x1 + width, y2: y1 + height }
  } else {
    const resized = { ...state.original }
    if (state.position.includes('w')) resized.x1 = Math.min(current.x, resized.x2 - minimum)
    if (state.position.includes('e')) resized.x2 = Math.max(current.x, resized.x1 + minimum)
    if (state.position.includes('n')) resized.y1 = Math.min(current.y, resized.y2 - minimum)
    if (state.position.includes('s')) resized.y2 = Math.max(current.y, resized.y1 + minimum)
    next[state.index] = resized
  }
  updateBoxes(next)
}
function finishDrag() {
  const state = dragState.value
  if (!state) return
  dragState.value = null
  const next = cloneBoxes()
  const box = next[state.index]
  if (!box || box.x2 - box.x1 < 2 || box.y2 - box.y1 < 2) {
    next.splice(state.index, 1)
    selectedIndex.value = next.length ? Math.min(state.index, next.length - 1) : -1
    updateBoxes(next)
  }
  emit('change')
}
function handles(box) {
  return [
    { position: 'nw', x: box.x1, y: box.y1 }, { position: 'ne', x: box.x2, y: box.y1 },
    { position: 'sw', x: box.x1, y: box.y2 }, { position: 'se', x: box.x2, y: box.y2 },
  ]
}
function removeSelected() {
  if (selectedIndex.value < 0) return
  const next = cloneBoxes()
  next.splice(selectedIndex.value, 1)
  selectedIndex.value = next.length ? Math.min(selectedIndex.value, next.length - 1) : -1
  updateBoxes(next)
  emit('change')
}
function clearBoxes() { selectedIndex.value = -1; updateBoxes([]); emit('change') }
</script>

<style scoped lang="scss">
.box-editor { min-width: 0; }
.editor-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.editor-toolbar span { color: $text-secondary; font-size: 12px; line-height: 1.5; }
.editor-toolbar div { display: flex; flex: 0 0 auto; gap: 6px; }
.canvas-shell { display: flex; align-items: center; justify-content: center; min-height: 300px; overflow: hidden; border: 1px solid $border-color; border-radius: 10px; background: #151922; }
.annotation-canvas { display: block; width: 100%; max-height: min(56vh, 560px); touch-action: none; user-select: none; }
.draw-surface { fill: transparent; cursor: crosshair; }
.annotation-box { fill: rgba(47, 111, 223, 0.12); stroke: #4f8aef; stroke-width: 2; vector-effect: non-scaling-stroke; cursor: move; }
.annotation-box.selected { fill: rgba(39, 132, 84, 0.14); stroke: #35a66c; stroke-width: 3; }
.resize-handle { fill: #fff; stroke: #278454; stroke-width: 2; vector-effect: non-scaling-stroke; cursor: nwse-resize; }
.box-label { pointer-events: none; }
.box-label rect { fill: #2f6fdf; opacity: 0.92; }
.box-label text { fill: #fff; font-weight: 600; }
</style>
