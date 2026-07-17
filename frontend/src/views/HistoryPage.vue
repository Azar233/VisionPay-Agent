<template>
  <div class="history-page">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Detection Records</span>
        <h1>识别历史</h1>
        <p>追溯当前账号发起的单图、批量、ZIP 与视频识别任务。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="refreshAll">刷新</el-button>
    </header>

    <section class="summary-grid">
      <article><span>全部任务</span><strong>{{ summary.total_tasks }}</strong></article>
      <article><span>今日新增</span><strong>{{ summary.today_tasks }}</strong></article>
      <article><span>已完成</span><strong>{{ summary.status_counts.completed }}</strong></article>
      <article><span>进行中</span><strong>{{ activeTasks }}</strong></article>
    </section>

    <section class="records-panel">
      <div class="filters">
        <el-input class="filter-keyword" v-model.trim="filters.keyword" clearable placeholder="搜索任务 ID 或场景" :prefix-icon="Search" @keyup.enter="applyFilters" />
        <el-select class="filter-select" v-model="filters.task_type" clearable placeholder="识别方式">
          <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select class="filter-select" v-model="filters.status" clearable placeholder="任务状态">
          <el-option label="已完成" value="completed" /><el-option label="处理中" value="processing" />
          <el-option label="等待中" value="pending" /><el-option label="失败" value="failed" />
        </el-select>
        <el-select class="filter-select" v-model="filters.scene_id" clearable placeholder="业务场景">
          <el-option v-for="scene in scenes" :key="scene.id" :label="scene.display_name" :value="scene.id" />
        </el-select>
        <el-date-picker class="filter-dates" v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" />
        <div class="filter-actions">
          <el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="tasks" row-key="id" empty-text="暂无识别记录">
        <el-table-column prop="id" label="任务" width="92">
          <template #default="{ row }"><strong class="task-id">#{{ row.id }}</strong></template>
        </el-table-column>
        <el-table-column label="识别方式" min-width="120">
          <template #default="{ row }"><span>{{ typeLabel(row.task_type) }}</span></template>
        </el-table-column>
        <el-table-column prop="scene_name" label="业务场景" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="104">
          <template #default="{ row }"><el-tag :type="statusMeta(row.status).tone" effect="light" round>{{ statusMeta(row.status).label }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="total_images" label="图片 / 帧" width="100" align="right" />
        <el-table-column prop="total_objects" label="商品实例" width="100" align="right" />
        <el-table-column label="平均耗时" width="112" align="right">
          <template #default="{ row }">{{ Number(row.avg_inference_time || 0).toFixed(1) }} ms</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="164">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="history-row-actions">
              <el-button class="history-action-button is-primary-action" size="small" :icon="View" @click="openDetail(row)">详情</el-button>
              <el-button class="history-action-button is-danger-action" size="small" :icon="Delete" @click="removeTask(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <footer class="pagination-row">
        <span>共 {{ pagination.total }} 条记录</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          layout="sizes, prev, pager, next"
          @current-change="loadTasks"
          @size-change="handleSizeChange"
        />
      </footer>
    </section>

    <el-drawer v-model="detailVisible" :title="detail?.task ? `识别任务 #${detail.task.id}` : '任务详情'" size="min(720px, 92vw)">
      <div v-loading="detailLoading" class="detail-content">
        <template v-if="detail?.task">
          <section class="detail-summary">
            <div><span>识别方式</span><strong>{{ typeLabel(detail.task.task_type) }}</strong></div>
            <div><span>状态</span><strong>{{ statusMeta(detail.task.status).label }}</strong></div>
            <div><span>图片 / 帧</span><strong>{{ detail.task.total_images }}</strong></div>
            <div><span>商品实例</span><strong>{{ detail.task.total_objects }}</strong></div>
          </section>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="业务场景">{{ detail.task.scene_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="平均推理">{{ Number(detail.task.avg_inference_time || 0).toFixed(1) }} ms</el-descriptions-item>
            <el-descriptions-item label="置信度阈值">{{ detail.task.conf_threshold }}</el-descriptions-item>
            <el-descriptions-item label="IoU 阈值">{{ detail.task.iou_threshold }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDate(detail.task.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ formatDate(detail.task.completed_at) }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.task.error_message" label="错误信息" :span="2">{{ detail.task.error_message }}</el-descriptions-item>
          </el-descriptions>

          <section class="class-summary">
            <h3>类别汇总</h3>
            <div v-if="Object.keys(detail.class_counts || {}).length" class="class-tags">
              <el-tag v-for="(count, name) in detail.class_counts" :key="name" effect="plain">{{ name }} × {{ count }}</el-tag>
            </div>
            <el-empty v-else description="本任务未识别到商品" :image-size="72" />
          </section>

          <section v-if="detail.results?.length" class="result-section">
            <h3>识别明细</h3>
            <el-table :data="detail.results" max-height="420" size="small">
              <el-table-column label="商品类别" min-width="150"><template #default="{ row }">{{ row.class_name_cn || row.class_name }}</template></el-table-column>
              <el-table-column label="置信度" width="96"><template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template></el-table-column>
              <el-table-column prop="image_path" label="来源图片 / 帧" min-width="210" show-overflow-tooltip />
              <el-table-column label="边界框" min-width="180"><template #default="{ row }">{{ row.bbox?.join(', ') }}</template></el-table-column>
            </el-table>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Delete, Refresh, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteTask, getHistorySummary, getScenes, getTaskDetail, getTaskList } from '@/api/history'

const typeOptions = [
  { value: 'single', label: '单图识别' }, { value: 'batch', label: '批量识别' },
  { value: 'zip', label: 'ZIP 识别' }, { value: 'video', label: '视频识别' },
  { value: 'camera', label: '实时摄像头' },
]
const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const tasks = ref([])
const scenes = ref([])
const detail = ref(null)
const summary = reactive({ total_tasks: 0, today_tasks: 0, status_counts: { completed: 0, processing: 0, pending: 0, failed: 0 } })
const filters = reactive({ keyword: '', task_type: '', status: '', scene_id: null, dateRange: [] })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })
const activeTasks = computed(() => (summary.status_counts.processing || 0) + (summary.status_counts.pending || 0))

function typeLabel(value) {
  return typeOptions.find((item) => item.value === value)?.label || value || '—'
}

function statusMeta(value) {
  return {
    completed: { label: '已完成', tone: 'success' }, processing: { label: '处理中', tone: 'warning' },
    pending: { label: '等待中', tone: 'info' }, failed: { label: '失败', tone: 'danger' },
  }[value] || { label: value || '未知', tone: 'info' }
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}

function queryParams() {
  const params = { page: pagination.page, page_size: pagination.pageSize }
  for (const key of ['keyword', 'task_type', 'status', 'scene_id']) if (filters[key] !== '' && filters[key] != null) params[key] = filters[key]
  if (filters.dateRange?.length === 2) [params.start_date, params.end_date] = filters.dateRange
  return params
}

async function loadTasks() {
  loading.value = true
  try {
    const data = await getTaskList(queryParams())
    tasks.value = data.items || []
    pagination.total = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  const data = await getHistorySummary()
  summary.total_tasks = data.total_tasks || 0
  summary.today_tasks = data.today_tasks || 0
  summary.status_counts = { ...summary.status_counts, ...(data.status_counts || {}) }
}

async function refreshAll() {
  try {
    await Promise.all([loadTasks(), loadSummary()])
  } catch {
    ElMessage.error('历史记录加载失败')
  }
}

function applyFilters() { pagination.page = 1; loadTasks() }
function resetFilters() {
  Object.assign(filters, { keyword: '', task_type: '', status: '', scene_id: null, dateRange: [] })
  pagination.page = 1
  loadTasks()
}
function handleSizeChange() { pagination.page = 1; loadTasks() }

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try { detail.value = await getTaskDetail(row.id) }
  catch { detailVisible.value = false }
  finally { detailLoading.value = false }
}

async function removeTask(row) {
  try {
    await ElMessageBox.confirm(`删除任务 #${row.id} 后，其识别明细也会一并删除。`, '删除识别记录', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await deleteTask(row.id)
    ElMessage.success('识别记录已删除')
    if (tasks.value.length === 1 && pagination.page > 1) pagination.page -= 1
    await refreshAll()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败，请稍后重试')
  }
}

onMounted(async () => {
  try {
    const sceneData = await getScenes()
    scenes.value = sceneData.scenes || []
  } catch { scenes.value = [] }
  await refreshAll()
})
</script>

<style lang="scss" scoped>
.history-page { min-height: 100%; padding: 32px; display: flex; flex-direction: column; gap: 18px; }
.page-header { padding: 30px 32px; display: flex; align-items: center; justify-content: space-between; gap: 24px; border: 1px solid $border-color; border-radius: $border-radius-lg; background: $surface-color; box-shadow: $shadow-sm; }.page-header h1 { margin: 8px 0 0; color: $text-primary; font-size: 38px; font-weight: 600; letter-spacing: -.045em; }.page-header p { margin: 9px 0 0; color: $text-secondary; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }.summary-grid article { padding: 20px 22px; display: flex; align-items: center; justify-content: space-between; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }.summary-grid span { color: $text-secondary; font-size: 12px; }.summary-grid strong { color: $text-primary; font-size: 25px; font-weight: 600; }
.records-panel { container: history-records / inline-size; overflow: hidden; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }
.filters { padding: 18px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; overflow: hidden; border-bottom: 1px solid $border-color; }
.filter-keyword { min-width: 190px; flex: 1.35 1 220px; }
.filter-select { min-width: 132px; flex: 1 1 145px; }
.filter-dates { min-width: 270px; flex: 1.25 1 310px; }
.filter-actions { flex: 0 0 auto; display: flex; gap: 8px; margin-left: auto; }
.filters :deep(.el-input), .filters :deep(.el-select), .filters :deep(.el-date-editor) { max-width: 100%; }
.filters :deep(.el-date-editor.el-input__wrapper) { width: 100%; min-width: 0; }
.task-id { color: $primary-color; font-weight: 600; }.pagination-row { min-height: 66px; padding: 0 18px; display: flex; align-items: center; justify-content: space-between; gap: 18px; border-top: 1px solid $border-color; }.pagination-row > span { color: $text-secondary; font-size: 12px; }
.history-row-actions { display: grid; grid-template-columns: repeat(2, 74px); gap: 6px; width: max-content; max-width: 100%; padding: 4px 0; }
.history-action-button { width: 74px; min-width: 74px; height: 30px; min-height: 30px; margin: 0 !important; padding: 0 6px; border: 1px solid $border-strong; border-radius: 7px; color: $text-regular; background: $surface-color; box-shadow: none !important; font-size: 12px; font-weight: 500; white-space: nowrap; transition: border-color .18s ease, color .18s ease, background-color .18s ease; }
.history-action-button:hover, .history-action-button:focus-visible { border-color: $text-secondary; color: $text-primary; background: $surface-muted; }
.history-action-button.is-primary-action { border-color: $primary-color; color: $primary-color; background: $primary-soft; }
.history-action-button.is-primary-action:hover, .history-action-button.is-primary-action:focus-visible { border-color: $primary-hover; color: $primary-hover; background: color-mix(in srgb, $primary-color 22%, $surface-color); }
.history-action-button.is-danger-action { border-color: $danger-color; color: $danger-color; background: color-mix(in srgb, $danger-color 10%, $surface-color); }
.history-action-button.is-danger-action:hover, .history-action-button.is-danger-action:focus-visible { border-color: $danger-color; color: $danger-color; background: color-mix(in srgb, $danger-color 18%, $surface-color); }
.detail-content { min-height: 240px; display: flex; flex-direction: column; gap: 22px; }.detail-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }.detail-summary div { padding: 16px; display: flex; flex-direction: column; gap: 6px; border-radius: 12px; background: $surface-muted; }.detail-summary span { color: $text-secondary; font-size: 11px; }.detail-summary strong { color: $text-primary; font-size: 18px; }.class-summary h3, .result-section h3 { margin: 0 0 12px; color: $text-primary; font-size: 15px; }.class-tags { display: flex; flex-wrap: wrap; gap: 8px; }
@container history-records (max-width: 1060px) {
  .filter-keyword { flex-basis: calc(50% - 5px); }
  .filter-select { flex-basis: calc(33.333% - 7px); }
  .filter-dates { flex: 1 1 360px; }
  .filter-actions { margin-left: 0; justify-content: flex-end; }
}
@container history-records (max-width: 680px) {
  .filter-keyword, .filter-select, .filter-dates { width: 100%; min-width: 0; flex: 1 1 100%; }
  .filter-actions { width: 100%; flex: 1 1 100%; }
  .filter-actions :deep(.el-button) { min-height: 44px; flex: 1; }
}
@media (max-width: 800px) { .history-page { padding: 12px; }.page-header { padding: 24px; align-items: flex-start; }.summary-grid { grid-template-columns: repeat(2, 1fr); }.pagination-row { padding: 14px; align-items: flex-start; flex-direction: column; }.detail-summary { grid-template-columns: repeat(2, 1fr); } }

</style>
