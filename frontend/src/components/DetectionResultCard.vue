<template>
  <section class="result-card">
    <header class="result-header">
      <div><span class="eyebrow">识别结果</span><strong>{{ headerText }}</strong></div>
      <el-tag effect="plain" type="success">{{ result.model }}</el-tag>
    </header>
    <div v-if="isVideo" class="video-meta">
      <el-tag effect="plain">时长 {{ Number(result.duration_seconds || 0).toFixed(1) }}s</el-tag>
      <el-tag effect="plain">原始 {{ Number(result.fps || 0).toFixed(1) }} FPS</el-tag>
      <el-tag effect="plain">{{ result.video_resolution?.width }} × {{ result.video_resolution?.height }}</el-tag>
      <el-tag v-if="isTracked" effect="plain">峰值同时 {{ result.peak_simultaneous || 0 }} 件</el-tag>
      <span>{{ isTracked ? 'ByteTrack 跨帧去重统计；遮挡或快速移动可能造成少量误差' : '统计为各采样帧检测次数之和，不代表跨帧去重商品数' }}</span>
    </div>
    <div v-if="isVideo && result.annotated_video_url" class="annotated-video">
      <video controls preload="metadata" :src="result.annotated_video_url">
        您的浏览器不支持视频播放
      </video>
    </div>
    <div v-if="classes.length" class="class-strip">
      <div v-for="item in classes" :key="item.name" class="class-stat">
        <span class="swatch" :style="{ backgroundColor: item.color }"></span><span>{{ item.name }}</span><strong>{{ item.count }}</strong>
      </div>
    </div>
    <el-empty v-else :image-size="54" description="当前阈值下未识别到商品" />
    <section v-if="result.price_summary" class="price-summary">
      <header>
        <div><span>商品总价</span><strong>{{ formatMoney(result.price_summary.total_price) }}</strong></div>
        <span
          class="vp-pill"
          :class="result.price_summary.pricing_complete ? 'vp-pill--success' : 'vp-pill--warning'"
        >
          {{ result.price_summary.pricing_complete ? '价格完整' : `${result.price_summary.unpriced_objects} 件未定价` }}
        </span>
      </header>
      <div v-if="result.price_summary.items?.length" class="price-items">
        <div v-for="item in result.price_summary.items" :key="item.class_id">
          <span>{{ item.name || item.class_name }} × {{ item.count }}</span>
          <strong v-if="item.has_price">{{ formatMoney(item.subtotal) }}</strong>
          <strong v-else class="missing-price">未定价</strong>
        </div>
      </div>
    </section>
    <div class="result-images">
      <article v-for="(item, index) in result.items" :key="`${item.filename}-${index}`" class="image-result">
        <button class="preview-button" type="button" @click="openPreview(item.annotated_image)">
          <img v-if="item.annotated_image" :src="item.annotated_image" :alt="`${item.filename} 检测标注图`" />
          <i v-else class="no-evidence">无证据帧</i>
          <span><el-icon><ZoomIn /></el-icon></span>
        </button>
        <div class="image-meta"><strong :title="item.filename">{{ itemTitle(item) }}</strong><span>{{ itemMeta(item) }}</span></div>
        <details v-if="item.detections.length" class="confidence-details">
          <summary>
            <span>商品置信度明细</span>
            <small>{{ item.detections.length }} 项</small>
          </summary>
          <el-table :data="item.detections" size="small" max-height="190">
            <el-table-column prop="class_name" label="商品类别" min-width="110" />
            <el-table-column label="置信度" width="92"><template #default="scope">{{ (scope.row.confidence * 100).toFixed(1) }}%</template></el-table-column>
          </el-table>
        </details>
      </article>
    </div>
    <el-dialog v-model="previewVisible" title="标注图预览" width="min(920px, 92vw)" append-to-body>
      <img class="dialog-image" :src="previewImage" alt="商品检测标注大图" />
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ZoomIn } from '@element-plus/icons-vue'

const props = defineProps({ result: { type: Object, required: true } })
const palette = ['#6366f1', '#10b981', '#d97706', '#dc2626', '#0891b2', '#7c3aed']
const previewVisible = ref(false)
const previewImage = ref('')
const isVideo = computed(() => props.result.source === 'video')
const isTracked = computed(() => props.result.object_count_mode === 'bytetrack_unique_tracks')
const headerText = computed(() => {
  if (!isVideo.value) return `${props.result.total_objects} 件商品 / ${props.result.total_images} 张图片`
  if (isTracked.value) return `${props.result.total_objects} 件商品（跨帧去重）/ 跟踪 ${props.result.processed_frames} 帧`
  return `${props.result.total_objects} 次采样检测 / ${props.result.processed_frames} 个关键帧`
})
const classes = computed(() => Object.entries(props.result.class_counts || {}).map(([name, count], index) => ({ name, count, color: palette[index % palette.length] })))
function openPreview(src) { if (!src) return; previewImage.value = src; previewVisible.value = true }
function itemTitle(item) {
  if (!isVideo.value) return item.filename
  if (isTracked.value) return `轨迹 #${item.track_id} · ${item.class_name || '未知类别'}`
  return `帧 ${item.frame_index} · ${Number(item.timestamp_seconds || 0).toFixed(2)}s`
}
function itemMeta(item) {
  if (isTracked.value) return `出现 ${Number(item.duration || 0).toFixed(1)}s · 置信度 ${Math.round((item.best_confidence || 0) * 100)}%`
  return `${item.object_count} 件 · ${formatTime(item.inference_time_ms)}`
}
function formatTime(value) { return Number(value || 0) < 1000 ? `${Number(value || 0).toFixed(0)} ms` : `${(value / 1000).toFixed(2)} s` }
function formatMoney(value) { return `¥ ${Number(value || 0).toFixed(2)}` }
</script>

<style lang="scss" scoped>
.result-card { margin-top: 14px; border: 1px solid $border-color; border-radius: $border-radius-md; overflow: hidden; background: $surface-color; box-shadow: $shadow-sm; }
.result-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 16px; border-bottom: 1px solid $border-color; }
.result-header > div { display: flex; flex-direction: column; gap: 3px; }
.result-header strong { color: $text-primary; font-size: 15px; }
.eyebrow { color: $text-secondary; font-size: 11px; font-weight: 700; }
.video-meta { display: flex; align-items: center; gap: 7px; padding: 9px 16px; overflow-x: auto; border-bottom: 1px solid $border-color; background: $surface-muted; }
.video-meta > * { flex-shrink: 0; }
.video-meta > span { color: $text-secondary; font-size: 10px; }
.annotated-video { padding: 12px 16px; border-bottom: 1px solid $border-color; background: $surface-muted; }
.annotated-video video { display: block; width: 100%; max-height: 480px; border-radius: $border-radius-sm; background: #000; }
.class-strip { display: flex; gap: 8px; padding: 10px 16px; overflow-x: auto; background: $surface-muted; }
.class-stat { display: grid; grid-template-columns: 8px auto auto; align-items: center; gap: 7px; min-width: max-content; padding: 6px 10px; border: 1px solid $border-color; border-radius: $border-radius-sm; background: $surface-color; font-size: 12px; }
.class-stat strong { margin-left: 4px; }
.swatch { width: 8px; height: 8px; border-radius: 2px; }
.price-summary { padding: 13px 16px; border-top: 1px solid $border-color; background: $surface-muted; }
.price-summary > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.price-summary > header > div { display: flex; align-items: baseline; gap: 10px; }
.price-summary header span { color: $text-secondary; font-size: 12px; }
.price-summary header strong { color: $text-primary; font-size: 21px; }
.price-items { display: grid; gap: 6px; margin-top: 10px; }
.price-items > div { display: flex; justify-content: space-between; gap: 12px; font-size: 11px; }
.price-items > div > span { color: $text-secondary; }
.price-items > div > strong { color: $text-primary; }
.price-items .missing-price { color: $warning-color; }
.result-images { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 1px; background: $border-color; }
.image-result { min-width: 0; background: $surface-color; padding-bottom: 10px; }
.preview-button { position: relative; display: block; width: 100%; aspect-ratio: 16 / 10; border: 0; padding: 0; background: $surface-muted; cursor: zoom-in; overflow: hidden; }
.preview-button img { width: 100%; height: 100%; object-fit: contain; }
.no-evidence { display: grid; place-items: center; width: 100%; height: 100%; color: $text-placeholder; font-size: 12px; font-style: normal; }
.preview-button span { position: absolute; right: 10px; bottom: 10px; display: grid; place-items: center; width: 30px; height: 30px; border-radius: $border-radius-sm; color: #fff; background: color-mix(in srgb, $bg-color-dark 76%, transparent); opacity: 0; transition: opacity .2s; }
.preview-button:hover span { opacity: 1; }
.image-meta { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; font-size: 12px; color: $text-secondary; }
.image-meta strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: $text-primary; }
.confidence-details { margin: 0 12px; overflow: hidden; border: 1px solid $border-color; border-radius: $border-radius-sm; background: $surface-color; }
.confidence-details summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 38px; padding: 0 11px; color: $text-secondary; background: $surface-muted; cursor: pointer; font-size: 12px; font-weight: 600; list-style: none; user-select: none; }
.confidence-details summary::-webkit-details-marker { display: none; }
.confidence-details summary::after { content: ''; width: 7px; height: 7px; flex: none; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(45deg) translate(-1px, 1px); transition: transform .2s ease; }
.confidence-details[open] summary::after { transform: rotate(225deg) translate(-1px, 1px); }
.confidence-details summary span { flex: 1; }
.confidence-details summary small { color: $text-placeholder; font-size: 10px; font-weight: 500; }
.confidence-details :deep(.el-table) { width: 100%; border-top: 1px solid $border-color; }
.image-result :deep(.el-table th.el-table__cell) { color: $text-secondary; font-weight: 600; background: $surface-muted; }
.dialog-image { display: block; max-width: 100%; max-height: 72vh; margin: auto; object-fit: contain; }
</style>
