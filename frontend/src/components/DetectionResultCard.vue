<template>
  <section class="result-card">
    <header class="result-header">
      <div><span class="eyebrow">识别结果</span><strong>{{ result.total_objects }} 件商品 / {{ result.total_images }} 张图片</strong></div>
      <el-tag effect="plain" type="success">{{ result.model }}</el-tag>
    </header>
    <div v-if="classes.length" class="class-strip">
      <div v-for="item in classes" :key="item.name" class="class-stat">
        <span class="swatch" :style="{ backgroundColor: item.color }"></span><span>{{ item.name }}</span><strong>{{ item.count }}</strong>
      </div>
    </div>
    <el-empty v-else :image-size="54" description="当前阈值下未识别到商品" />
    <div class="result-images">
      <article v-for="(item, index) in result.items" :key="`${item.filename}-${index}`" class="image-result">
        <button class="preview-button" type="button" @click="openPreview(item.annotated_image)">
          <img :src="item.annotated_image" :alt="`${item.filename} 检测标注图`" />
          <span><el-icon><ZoomIn /></el-icon></span>
        </button>
        <div class="image-meta"><strong :title="item.filename">{{ item.filename }}</strong><span>{{ item.object_count }} 件 · {{ formatTime(item.inference_time_ms) }}</span></div>
        <el-table v-if="item.detections.length" :data="item.detections" size="small" max-height="190">
          <el-table-column prop="class_name" label="商品类别" min-width="110" />
          <el-table-column label="置信度" width="92"><template #default="scope">{{ (scope.row.confidence * 100).toFixed(1) }}%</template></el-table-column>
        </el-table>
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
const classes = computed(() => Object.entries(props.result.class_counts || {}).map(([name, count], index) => ({ name, count, color: palette[index % palette.length] })))
function openPreview(src) { previewImage.value = src; previewVisible.value = true }
function formatTime(value) { return Number(value || 0) < 1000 ? `${Number(value || 0).toFixed(0)} ms` : `${(value / 1000).toFixed(2)} s` }
</script>

<style lang="scss" scoped>
.result-card { margin-top: 14px; border: 1px solid $border-color; border-radius: $border-radius-md; overflow: hidden; background: $surface-color; box-shadow: $shadow-sm; }
.result-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 16px; border-bottom: 1px solid $border-color; }
.result-header > div { display: flex; flex-direction: column; gap: 3px; }
.result-header strong { color: $text-primary; font-size: 15px; }.eyebrow { color: $text-secondary; font-size: 11px; font-weight: 700; }
.class-strip { display: flex; gap: 8px; padding: 10px 16px; overflow-x: auto; background: $surface-muted; }
.class-stat { display: grid; grid-template-columns: 8px auto auto; align-items: center; gap: 7px; min-width: max-content; padding: 6px 10px; border: 1px solid $border-color; border-radius: $border-radius-sm; background: $surface-color; font-size: 12px; }
.class-stat strong { margin-left: 4px; }.swatch { width: 8px; height: 8px; border-radius: 2px; }
.result-images { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 1px; background: $border-color; }
.image-result { min-width: 0; background: $surface-color; padding-bottom: 10px; }.preview-button { position: relative; display: block; width: 100%; aspect-ratio: 16 / 10; border: 0; padding: 0; background: $surface-muted; cursor: zoom-in; overflow: hidden; }
.preview-button img { width: 100%; height: 100%; object-fit: contain; }.preview-button span { position: absolute; right: 10px; bottom: 10px; display: grid; place-items: center; width: 30px; height: 30px; border-radius: $border-radius-sm; color: #fff; background: rgba(17, 24, 39, .76); opacity: 0; transition: opacity .2s; }
.preview-button:hover span { opacity: 1; }.image-meta { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; font-size: 12px; color: #6b7785; }
.image-meta strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: $text-primary; }.image-result :deep(.el-table) { width: calc(100% - 24px); margin: 0 12px; }.dialog-image { display: block; max-width: 100%; max-height: 72vh; margin: auto; object-fit: contain; }
</style>
