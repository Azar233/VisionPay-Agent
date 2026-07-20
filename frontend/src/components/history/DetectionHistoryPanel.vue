<template>
  <section class="history-panel">
    <div class="filters">
      <el-input
        v-model.trim="filters.keyword"
        clearable
        placeholder="搜索任务 ID 或场景"
        :prefix-icon="Search"
        @keyup.enter="applyFilters"
      />
      <el-select v-model="filters.task_type" clearable placeholder="识别方式">
        <el-option
          v-for="item in typeOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="任务状态">
        <el-option label="已完成" value="completed" /><el-option
          label="处理中"
          value="processing"
        />
        <el-option label="等待中" value="pending" /><el-option label="失败" value="failed" />
      </el-select>
      <el-select v-model="filters.scene_id" clearable placeholder="业务场景">
        <el-option
          v-for="scene in scenes"
          :key="scene.id"
          :label="scene.display_name"
          :value="scene.id"
        />
      </el-select>
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
      />
      <div class="filter-actions">
        <el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button
        ><el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="tasks" row-key="id" empty-text="暂无识别记录">
      <el-table-column label="任务" width="86"
        ><template #default="{ row }"
          ><strong class="record-id">#{{ row.id }}</strong></template
        ></el-table-column
      >
      <el-table-column label="识别方式" min-width="116"
        ><template #default="{ row }">{{ typeLabel(row.task_type) }}</template></el-table-column
      >
      <el-table-column prop="scene_name" label="业务场景" min-width="145" show-overflow-tooltip />
      <el-table-column label="状态" width="104"
        ><template #default="{ row }"
          ><el-tag :type="statusMeta(row.status).tone" effect="light" round>{{
            statusMeta(row.status).label
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="total_images" label="图片 / 帧" width="96" align="right" />
      <el-table-column prop="total_objects" label="商品实例" width="96" align="right" />
      <el-table-column label="平均耗时" width="108" align="right"
        ><template #default="{ row }"
          >{{ Number(row.avg_inference_time || 0).toFixed(1) }} ms</template
        ></el-table-column
      >
      <el-table-column label="创建时间" min-width="164"
        ><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column
      >
      <el-table-column label="操作" width="190" fixed="right" align="center"
        ><template #default="{ row }"
          ><div class="row-actions vp-table-action-safe-area">
            <el-button
              class="vp-table-action-button"
              size="small"
              :icon="View"
              @click="openDetail(row)"
              >详情</el-button
            ><el-button
              class="vp-table-action-button is-danger-action"
              size="small"
              type="danger"
              plain
              :icon="Delete"
              @click="removeTask(row)"
              >删除</el-button
            >
          </div></template
        ></el-table-column
      >
    </el-table>

    <footer class="pagination-row">
      <span>共 {{ pagination.total }} 条记录</span
      ><el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        layout="sizes, prev, pager, next"
        @current-change="loadTasks"
        @size-change="handleSizeChange"
      />
    </footer>

    <el-drawer
      v-model="detailVisible"
      :title="detail?.task ? `识别任务 #${detail.task.id}` : '任务详情'"
      size="min(720px, 92vw)"
      append-to-body
    >
      <div v-loading="detailLoading" class="detail-content">
        <template v-if="detail?.task">
          <section class="detail-summary">
            <div>
              <span>识别方式</span><strong>{{ typeLabel(detail.task.task_type) }}</strong>
            </div>
            <div>
              <span>状态</span><strong>{{ statusMeta(detail.task.status).label }}</strong>
            </div>
            <div>
              <span>图片 / 帧</span><strong>{{ detail.task.total_images }}</strong>
            </div>
            <div>
              <span>商品实例</span><strong>{{ detail.task.total_objects }}</strong>
            </div>
          </section>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="业务场景">{{
              detail.task.scene_name || '—'
            }}</el-descriptions-item>
            <el-descriptions-item label="平均推理"
              >{{ Number(detail.task.avg_inference_time || 0).toFixed(1) }} ms</el-descriptions-item
            >
            <el-descriptions-item label="置信度阈值">{{
              detail.task.conf_threshold
            }}</el-descriptions-item>
            <el-descriptions-item label="IoU 阈值">{{
              detail.task.iou_threshold
            }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{
              formatDate(detail.task.created_at)
            }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{
              formatDate(detail.task.completed_at)
            }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.task.error_message" label="错误信息" :span="2">{{
              detail.task.error_message
            }}</el-descriptions-item>
          </el-descriptions>
          <section class="detail-section">
            <h3>类别汇总</h3>
            <div v-if="Object.keys(detail.class_counts || {}).length" class="tag-list">
              <el-tag v-for="(count, name) in detail.class_counts" :key="name" effect="plain"
                >{{ name }} × {{ count }}</el-tag
              >
            </div>
            <el-empty v-else description="本任务未识别到商品" :image-size="72" />
          </section>
          <section v-if="detail.results?.length" class="detail-section">
            <h3>识别明细</h3>
            <el-table :data="detail.results" max-height="420" size="small"
              ><el-table-column label="商品类别" min-width="150"
                ><template #default="{ row }">{{
                  row.class_name_cn || row.class_name
                }}</template></el-table-column
              ><el-table-column label="置信度" width="96"
                ><template #default="{ row }"
                  >{{ (row.confidence * 100).toFixed(1) }}%</template
                ></el-table-column
              ><el-table-column
                prop="image_path"
                label="来源图片 / 帧"
                min-width="210"
                show-overflow-tooltip
              /><el-table-column label="边界框" min-width="180"
                ><template #default="{ row }">{{ row.bbox?.join(', ') }}</template></el-table-column
              ></el-table
            >
          </section>
        </template>
      </div>
    </el-drawer>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Delete, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteTask, getScenes, getTaskDetail, getTaskList } from '@/api/history'

const emit = defineEmits(['changed'])
const typeOptions = [
  { value: 'single', label: '单图识别' },
  { value: 'batch', label: '批量识别' },
  { value: 'zip', label: 'ZIP 识别' },
  { value: 'video', label: '视频识别' },
  { value: 'camera', label: '实时摄像头' },
]
const statusOptions = {
  completed: { label: '已完成', tone: 'success' },
  processing: { label: '处理中', tone: 'warning' },
  pending: { label: '等待中', tone: 'info' },
  failed: { label: '失败', tone: 'danger' },
}
const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const tasks = ref([])
const scenes = ref([])
const detail = ref(null)
const filters = reactive({ keyword: '', task_type: '', status: '', scene_id: null, dateRange: [] })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

function typeLabel(value) {
  return typeOptions.find((item) => item.value === value)?.label || value || '—'
}

function statusMeta(value) {
  return statusOptions[value] || { label: value || '未知', tone: 'info' }
}

function formatDate(value) {
  if (!value) return '—'

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function queryParams() {
  const params = {
    page: pagination.page,
    page_size: pagination.pageSize,
  }

  for (const key of ['keyword', 'task_type', 'status', 'scene_id']) {
    if (filters[key] !== '' && filters[key] != null) params[key] = filters[key]
  }

  if (filters.dateRange?.length === 2) {
    ;[params.start_date, params.end_date] = filters.dateRange
  }

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

function applyFilters() {
  pagination.page = 1
  loadTasks()
}

function resetFilters() {
  Object.assign(filters, {
    keyword: '',
    task_type: '',
    status: '',
    scene_id: null,
    dateRange: [],
  })
  pagination.page = 1
  loadTasks()
}

function handleSizeChange() {
  pagination.page = 1
  loadTasks()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null

  try {
    detail.value = await getTaskDetail(row.id)
  } catch {
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function removeTask(row) {
  try {
    await ElMessageBox.confirm(`删除任务 #${row.id} 后，其识别明细也会一并删除。`, '删除识别记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      customClass: 'app-confirm-dialog',
    })
    await deleteTask(row.id)
    ElMessage.success('识别记录已删除')

    if (tasks.value.length === 1 && pagination.page > 1) {
      pagination.page -= 1
    }

    await loadTasks()
    emit('changed')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('删除失败，请稍后重试')
    }
  }
}

async function refresh() {
  try {
    await loadTasks()
  } catch {
    ElMessage.error('识别历史加载失败')
  }
}

defineExpose({ refresh })

onMounted(async () => {
  try {
    scenes.value = (await getScenes()).scenes || []
  } catch {
    scenes.value = []
  }
  await refresh()
})
</script>

<style lang="scss" scoped>
.history-panel {
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: 16px;
  background: $surface-color;
}
.filters {
  padding: 16px;
  display: grid;
  grid-template-columns:
    minmax(190px, 1.4fr) repeat(3, minmax(130px, 0.8fr)) minmax(270px, 1.3fr)
    auto;
  gap: 10px;
  border-bottom: 1px solid $border-color;
}
.filters > * {
  min-width: 0;
  width: 100%;
}
.filter-actions {
  display: flex;
  width: auto;
}
.record-id {
  color: $primary-color;
}
.row-actions {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  white-space: nowrap;
}
.pagination-row {
  min-height: 64px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid $border-color;
}
.pagination-row span {
  color: $text-secondary;
  font-size: 12px;
}
.detail-content {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.detail-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.detail-summary div {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border-radius: 12px;
  background: $surface-muted;
}
.detail-summary span {
  color: $text-secondary;
  font-size: 11px;
}
.detail-summary strong {
  font-size: 17px;
}
.detail-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 1180px) {
  .filters {
    grid-template-columns: repeat(3, 1fr);
  }
  .filter-actions {
    width: 100%;
  }
}
@media (max-width: 720px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .pagination-row {
    padding: 14px;
    align-items: flex-start;
    flex-direction: column;
  }
  .detail-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
