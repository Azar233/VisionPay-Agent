<template>
  <section class="history-panel">
    <div class="filters">
      <el-input
        v-model.trim="filters.keyword"
        clearable
        placeholder="搜索模型版本、名称或场景"
        :prefix-icon="Search"
        @keyup.enter="applyFilters"
      />
      <el-select v-model="filters.scene_id" clearable placeholder="业务场景"
        ><el-option
          v-for="scene in scenes"
          :key="scene.id"
          :label="scene.display_name"
          :value="scene.id"
      /></el-select>
      <el-select v-model="filters.status" clearable placeholder="模型状态"
        ><el-option label="活动" value="active" /><el-option
          label="已归档"
          value="archived" /><el-option label="已删除" value="deleted"
      /></el-select>
      <el-select v-model="filters.origin" clearable placeholder="创建来源"
        ><el-option label="训练产出" value="training" /><el-option
          label="手动导入"
          value="imported" /><el-option label="内置模型" value="builtin"
      /></el-select>
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

    <el-table v-loading="loading" :data="items" row-key="id" empty-text="暂无模型历史记录">
      <el-table-column label="模型版本" min-width="205"
        ><template #default="{ row }"
          ><div class="model-identity">
            <span class="model-icon"
              ><el-icon><Cpu /></el-icon
            ></span>
            <div>
              <strong>{{ row.version }}</strong
              ><small>{{ row.model_name }}</small>
            </div>
          </div></template
        ></el-table-column
      >
      <el-table-column label="来源" width="110"
        ><template #default="{ row }"
          ><el-tag effect="plain" round>{{ originLabel(row.origin) }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="scene_name" label="业务场景" min-width="145" show-overflow-tooltip />
      <el-table-column label="数据集" min-width="130" show-overflow-tooltip
        ><template #default="{ row }">{{
          row.dataset_version || '未绑定'
        }}</template></el-table-column
      >
      <el-table-column label="状态" width="118"
        ><template #default="{ row }"
          ><div class="status-stack">
            <span class="vp-pill" :class="`vp-pill--${modelStatusType(row.status)}`">{{
              modelStatusText(row.status)
            }}</span
            ><span v-if="row.is_default">默认</span>
          </div></template
        ></el-table-column
      >
      <el-table-column label="操作次数" width="92" align="center"
        ><template #default="{ row }">{{ row.operation_count }}</template></el-table-column
      >
      <el-table-column label="创建时间" min-width="166"
        ><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column
      >
      <el-table-column label="最近操作" min-width="166"
        ><template #default="{ row }">{{
          formatDate(row.latest_operation_at)
        }}</template></el-table-column
      >
      <el-table-column label="操作" width="104" fixed="right" align="center"
        ><template #default="{ row }"
          ><div class="vp-table-action-safe-area">
            <el-button
              class="vp-table-action-button"
              size="small"
              :icon="View"
              @click="openDetail(row)"
              >详情</el-button
            >
          </div></template
        ></el-table-column
      >
    </el-table>

    <footer class="pagination-row">
      <span>共 {{ pagination.total }} 个模型版本</span
      ><el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        layout="sizes, prev, pager, next"
        @current-change="loadItems"
        @size-change="handleSizeChange"
      />
    </footer>

    <el-drawer
      v-model="detailVisible"
      :title="detail?.model ? `模型 ${detail.model.version}` : '模型历史详情'"
      size="min(800px, 94vw)"
      append-to-body
    >
      <div v-loading="detailLoading" class="detail-content">
        <template v-if="detail?.model">
          <div class="model-hero">
            <span
              ><el-icon><Cpu /></el-icon
            ></span>
            <div>
              <small>{{ originLabel(detail.model.origin) }}</small>
              <h3>{{ detail.model.version }}</h3>
              <p>{{ detail.model.model_name }}</p>
            </div>
            <div class="hero-tags">
              <el-tag :type="detail.model.status === 'active' ? 'success' : 'info'" round>{{
                detail.model.status === 'active' ? '活动' : '已归档'
              }}</el-tag
              ><el-tag v-if="detail.model.is_default" type="primary" round>当前默认</el-tag>
            </div>
          </div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="业务场景">{{
              detail.model.scene_name || '—'
            }}</el-descriptions-item>
            <el-descriptions-item label="模型类型">{{
              detail.model.model_type || '—'
            }}</el-descriptions-item>
            <el-descriptions-item label="数据集版本">{{
              detail.model.dataset_version || '未绑定'
            }}</el-descriptions-item>
            <el-descriptions-item label="训练任务">{{
              detail.model.training_task_uuid || '非训练产出'
            }}</el-descriptions-item>
            <el-descriptions-item label="创建人员">{{
              detail.model.created_by || '系统'
            }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{
              formatDate(detail.model.created_at)
            }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.model.description" label="说明" :span="2">{{
              detail.model.description
            }}</el-descriptions-item>
          </el-descriptions>
          <section v-if="hasMetrics" class="metric-grid">
            <div>
              <span>Precision</span><strong>{{ metric(detail.model.precision) }}</strong>
            </div>
            <div>
              <span>Recall</span><strong>{{ metric(detail.model.recall) }}</strong>
            </div>
            <div>
              <span>mAP50</span><strong>{{ metric(detail.model.map50) }}</strong>
            </div>
            <div>
              <span>mAP50-95</span><strong>{{ metric(detail.model.map50_95) }}</strong>
            </div>
          </section>
          <section class="timeline-section">
            <div class="section-title">
              <div>
                <span>Lifecycle Timeline</span>
                <h4>模型生命周期</h4>
              </div>
              <em>{{ detail.events?.length || 0 }} 个事件</em>
            </div>
            <el-timeline v-if="detail.events?.length"
              ><el-timeline-item
                v-for="event in detail.events"
                :key="event.id"
                :timestamp="formatDate(event.created_at)"
                placement="top"
                :type="eventType(event)"
                ><article class="event-card">
                  <div>
                    <strong>{{ event.action_label }}</strong
                    ><el-tag
                      :type="event.status === 'success' ? 'success' : 'danger'"
                      size="small"
                      effect="plain"
                      >{{ event.status === 'success' ? '成功' : '失败' }}</el-tag
                    >
                  </div>
                  <p>{{ event.description || '没有补充说明' }}</p>
                  <small>执行者：{{ event.actor || '系统' }}</small>
                </article></el-timeline-item
              ></el-timeline
            ><el-empty v-else description="暂无生命周期事件" :image-size="72" />
          </section>
        </template>
      </div>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Cpu, Search, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getModelHistoryDetail, getModelHistoryList, getScenes } from '@/api/history'

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const detail = ref(null)
const items = ref([])
const scenes = ref([])
const filters = reactive({ keyword: '', scene_id: null, status: '', origin: '', dateRange: [] })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })
const hasMetrics = computed(
  () =>
    detail.value?.model &&
    ['precision', 'recall', 'map50', 'map50_95'].some((key) => detail.value.model[key] != null),
)
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
function originLabel(value) {
  return (
    { training: '训练产出', imported: '手动导入', builtin: '内置模型' }[value] || value || '未知'
  )
}
// 与数据集页一致的状态点样式（vp-pill）。
function modelStatusType(status) {
  return { active: 'success', archived: 'info', deleted: 'danger' }[status] || 'info'
}
function modelStatusText(status) {
  return { active: '活动', archived: '已归档', deleted: '已删除' }[status] || status || '未知'
}
function metric(value) {
  return value == null ? '—' : Number(value).toFixed(4)
}
function eventType(event) {
  if (event.status !== 'success') return 'danger'
  return (
    {
      created: 'primary',
      set_default: 'success',
      auto_set_default: 'success',
      unset_default: 'warning',
      archive: 'info',
    }[event.action] || 'primary'
  )
}
function queryParams() {
  const params = { page: pagination.page, page_size: pagination.pageSize }
  for (const key of ['keyword', 'scene_id', 'status', 'origin'])
    if (filters[key] !== '' && filters[key] != null) params[key] = filters[key]
  if (filters.dateRange?.length === 2) [params.start_date, params.end_date] = filters.dateRange
  return params
}
async function loadItems() {
  loading.value = true
  try {
    const data = await getModelHistoryList(queryParams())
    items.value = data.items || []
    pagination.total = data.total || 0
  } finally {
    loading.value = false
  }
}
function applyFilters() {
  pagination.page = 1
  refresh()
}
function resetFilters() {
  Object.assign(filters, { keyword: '', scene_id: null, status: '', origin: '', dateRange: [] })
  pagination.page = 1
  refresh()
}
function handleSizeChange() {
  pagination.page = 1
  loadItems()
}
async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getModelHistoryDetail(row.id)
  } catch {
    detailVisible.value = false
    ElMessage.error('模型历史详情加载失败')
  } finally {
    detailLoading.value = false
  }
}
async function refresh() {
  try {
    await loadItems()
  } catch {
    ElMessage.error('模型历史加载失败')
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
    minmax(210px, 1.3fr) repeat(3, minmax(125px, 0.7fr)) minmax(260px, 1.15fr)
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
.model-identity {
  display: flex;
  align-items: center;
  gap: 10px;
}
.model-icon {
  width: 34px;
  height: 34px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 10px;
  color: $primary-color;
  background: $primary-soft;
}
.model-identity div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.model-identity strong,
.model-identity small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-identity small {
  color: $text-placeholder;
}
.status-stack {
  display: flex;
  align-items: center;
  gap: 5px;
}
.status-stack > span:not(.vp-pill) {
  color: $primary-color;
  font-size: 10px;
  font-weight: 800;
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
  min-height: 240px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.model-hero {
  display: grid;
  grid-template-columns: 58px 1fr auto;
  align-items: center;
  gap: 14px;
}
.model-hero > span {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(145deg, $primary-color, #6366f1);
  font-size: 24px;
}
.model-hero small {
  color: $primary-color;
  font-size: 10px;
  font-weight: 800;
}
.model-hero h3 {
  margin: 3px 0;
  font-size: 21px;
}
.model-hero p {
  margin: 0;
  color: $text-secondary;
}
.hero-tags {
  display: flex;
  gap: 6px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.metric-grid div {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border-radius: 12px;
  background: $surface-muted;
}
.metric-grid span {
  color: $text-secondary;
  font-size: 10px;
}
.metric-grid strong {
  font-size: 17px;
}
.section-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 14px;
}
.section-title span {
  color: $primary-color;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.section-title h4 {
  margin: 3px 0 0;
  font-size: 17px;
}
.section-title em {
  color: $text-placeholder;
  font-size: 11px;
  font-style: normal;
}
.event-card {
  padding: 13px 15px;
  border: 1px solid $border-color;
  border-radius: 12px;
  background: $surface-muted;
}
.event-card > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.event-card p {
  margin: 8px 0;
  color: $text-secondary;
  line-height: 1.6;
}
.event-card small {
  color: $text-placeholder;
}
@media (max-width: 1180px) {
  .filters {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 680px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .pagination-row {
    padding: 14px;
    align-items: flex-start;
    flex-direction: column;
  }
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .model-hero {
    grid-template-columns: 52px 1fr;
  }
  .hero-tags {
    grid-column: 1 / -1;
  }
}
</style>
