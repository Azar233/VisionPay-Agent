<template>
  <section class="history-panel">
    <div class="filters">
      <el-input v-model.trim="filters.keyword" clearable placeholder="搜索用户请求、回复或会话" :prefix-icon="Search" @keyup.enter="applyFilters" />
      <el-select v-model="filters.agent" clearable placeholder="调用的 Agent"><el-option v-for="item in agentOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
      <el-date-picker v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" />
      <div class="filter-actions"><el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button><el-button @click="resetFilters">重置</el-button></div>
    </div>

    <el-table v-loading="loading" :data="items" row-key="id" empty-text="暂无 Agent 调用记录">
      <el-table-column label="调用时间" min-width="166"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
      <el-table-column label="Agent" min-width="148"><template #default="{ row }"><div class="agent-stack"><span v-for="item in (row.agents?.length ? row.agents : [{ agent: row.agent, label: row.agent_label }])" :key="item.agent" :class="['agent-badge', item.agent]"><i></i>{{ item.label }}</span></div></template></el-table-column>
      <el-table-column label="用户请求" min-width="250" show-overflow-tooltip><template #default="{ row }"><span class="request-copy">{{ row.user_request || '—' }}</span></template></el-table-column>
      <el-table-column label="执行内容" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.action_label }}</template></el-table-column>
      <el-table-column label="附件" width="76" align="center"><template #default="{ row }">{{ row.attachment_count || '—' }}</template></el-table-column>
      <el-table-column label="Token" width="92" align="right"><template #default="{ row }">{{ row.tokens_used != null ? row.tokens_used.toLocaleString() : '—' }}</template></el-table-column>
      <el-table-column label="耗时" width="100" align="right"><template #default="{ row }">{{ row.latency_ms != null ? `${row.latency_ms} ms` : '—' }}</template></el-table-column>
      <el-table-column label="状态" width="94"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'danger'" effect="light" round>{{ row.status === 'completed' ? '已完成' : '失败' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="104" fixed="right" align="center"><template #default="{ row }"><div class="vp-table-action-safe-area"><el-button class="vp-table-action-button" size="small" :icon="View" @click="openDetail(row)">详情</el-button></div></template></el-table-column>
    </el-table>

    <footer class="pagination-row"><span>共 {{ pagination.total }} 次调用</span><el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize" :page-sizes="[10,20,50]" :total="pagination.total" layout="sizes, prev, pager, next" @current-change="loadItems" @size-change="handleSizeChange" /></footer>

    <el-drawer v-model="detailVisible" title="Agent 调用详情" size="min(760px, 94vw)" append-to-body>
      <div v-loading="detailLoading" class="detail-content">
        <template v-if="detail">
          <div class="detail-heading"><span :class="['agent-orb', detail.agent]">{{ agentInitial(detail.agent) }}</span><div><small>调用 #{{ detail.id }}</small><h3>{{ detail.agent_label }}</h3><p>{{ detail.action_label }}</p></div><el-tag :type="detail.status === 'completed' ? 'success' : 'danger'" round>{{ detail.status === 'completed' ? '已完成' : '失败' }}</el-tag></div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="调用时间">{{ formatDate(detail.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ detail.latency_ms != null ? `${detail.latency_ms} ms` : '未记录' }}</el-descriptions-item>
            <el-descriptions-item label="模型总 Token">{{ detail.tokens_used != null ? detail.tokens_used.toLocaleString() : '模型未返回' }}</el-descriptions-item>
            <el-descriptions-item label="历史上下文 Token">{{ detail.context_tokens != null ? detail.context_tokens.toLocaleString() : '未记录' }}</el-descriptions-item>
            <el-descriptions-item label="输入 / 输出 Token">{{ detail.model_usage ? `${detail.model_usage.input_tokens || 0} / ${detail.model_usage.output_tokens || 0}` : '模型未返回' }}</el-descriptions-item>
            <el-descriptions-item label="会话">{{ detail.session_title || '未命名会话' }}</el-descriptions-item>
            <el-descriptions-item label="会话 ID"><span class="mono">{{ detail.session_uuid }}</span></el-descriptions-item>
            <el-descriptions-item label="路由方式">{{ routeMethod(detail.routing?.method) }}</el-descriptions-item>
            <el-descriptions-item label="路由置信度">{{ detail.routing?.confidence != null ? `${(detail.routing.confidence * 100).toFixed(1)}%` : '未记录' }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.routing?.reason" label="路由依据" :span="2">{{ detail.routing.reason }}</el-descriptions-item>
          </el-descriptions>
          <section class="content-card"><span>用户请求</span><p>{{ detail.user_request || '—' }}</p></section>
          <section class="content-card response"><span>Agent 回复</span><p>{{ detail.response || '—' }}</p></section>
          <section v-if="detail.tools?.length" class="detail-section"><h4>工具链</h4><div class="tool-chain"><template v-for="(tool,index) in detail.tools" :key="tool"><span>{{ toolLabel(tool) }}</span><el-icon v-if="index < detail.tools.length - 1"><ArrowRight /></el-icon></template></div></section>
          <section v-if="detail.attachments?.length" class="detail-section"><h4>附件</h4><div class="attachment-list"><span v-for="file in detail.attachments" :key="file.name || file"><el-icon><Document /></el-icon>{{ file.name || file }}</span></div></section>
        </template>
      </div>
    </el-drawer>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ArrowRight, Document, Search, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getAgentCallDetail, getAgentCallList } from '@/api/history'

const agentOptions = [
  { value: 'detection', label: 'Detection Agent' }, { value: 'dataset', label: 'Dataset Agent' },
  { value: 'training', label: 'Training Agent' }, { value: 'catalog', label: 'Catalog Agent' },
  { value: 'knowledge', label: 'Knowledge Agent' },
]
const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const detail = ref(null)
const items = ref([])
const filters = reactive({ keyword: '', agent: '', dateRange: [] })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })
function formatDate(value) { if (!value) return '—'; return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) }
function queryParams() { const params = { page: pagination.page, page_size: pagination.pageSize }; if (filters.keyword) params.keyword = filters.keyword; if (filters.agent) params.agent = filters.agent; if (filters.dateRange?.length === 2) [params.start_date, params.end_date] = filters.dateRange; return params }
async function loadItems() { loading.value = true; try { const data = await getAgentCallList(queryParams()); items.value = data.items || []; pagination.total = data.total || 0 } finally { loading.value = false } }
function applyFilters() { pagination.page = 1; refresh() }
function resetFilters() { Object.assign(filters, { keyword: '', agent: '', dateRange: [] }); pagination.page = 1; refresh() }
function handleSizeChange() { pagination.page = 1; loadItems() }
async function openDetail(row) { detailVisible.value = true; detailLoading.value = true; detail.value = null; try { detail.value = await getAgentCallDetail(row.id) } catch { detailVisible.value = false; ElMessage.error('Agent 调用详情加载失败') } finally { detailLoading.value = false } }
function agentInitial(agent) { return ({ detection: 'D', dataset: 'DS', training: 'T', catalog: 'C', knowledge: 'K' })[agent] || 'A' }
function routeMethod(value) { return ({ explicit_intent: '强意图路由', embedding: 'Embedding 语义路由', keyword: '关键词路由', attachment: '附件路由', attachment_intent: '附件意图路由', conversation_context: '会话上下文', form_submission: '表单工作流' })[value] || value || '历史记录未保存' }
function toolLabel(value) { return ({ list_dataset_versions: '读取数据集版本', get_current_dataset_version: '读取当前数据集', get_dataset_version_detail: '读取版本详情', list_training_tasks: '读取训练任务', get_training_status: '读取训练状态', get_training_metrics: '读取训练指标', list_product_prices: '读取价目表', search_management_knowledge: '检索知识库', search_fault_cases: '检索故障案例', request_user_input_form: '生成参数表单', detect_single_product_image: '单图商品检测', detect_multiple_product_images: '批量商品检测', detect_zip_product_images: 'ZIP 商品检测', detect_product_video: '视频商品检测' })[value] || value }
async function refresh() { try { await loadItems() } catch { ElMessage.error('Agent 调用历史加载失败') } }
defineExpose({ refresh })
onMounted(refresh)
</script>

<style lang="scss" scoped>
.history-panel { overflow: hidden; border: 1px solid $border-color; border-radius: 16px; background: $surface-color; }.filters { padding: 16px; display: grid; grid-template-columns: minmax(240px,1.5fr) minmax(160px,.7fr) minmax(280px,1fr) auto; gap: 10px; border-bottom: 1px solid $border-color; }.filters > * { width: 100%; min-width: 0; }.filter-actions { display: flex; width: auto; }
.agent-badge { display: inline-flex; align-items: center; gap: 7px; font-weight: 700; white-space: nowrap; }.agent-badge i { width: 8px; height: 8px; border-radius: 50%; background: $primary-color; }.agent-badge.dataset i { background: #8b5cf6; }.agent-badge.training i { background: #0ea5e9; }.agent-badge.catalog i { background: #f59e0b; }.agent-badge.knowledge i { background: #10b981; }.request-copy { color: $text-primary; }
// 并行调用时子 Agent 标识竖向排列。
.agent-stack { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; }
.pagination-row { min-height: 64px; padding: 0 18px; display: flex; align-items: center; justify-content: space-between; border-top: 1px solid $border-color; }.pagination-row span { color: $text-secondary; font-size: 12px; }
.detail-content { min-height: 220px; display: flex; flex-direction: column; gap: 20px; }.detail-heading { display: grid; grid-template-columns: 52px 1fr auto; align-items: center; gap: 13px; }.agent-orb { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 16px; color: #fff; background: $primary-color; font-weight: 800; }.agent-orb.dataset { background: #8b5cf6; }.agent-orb.training { background: #0ea5e9; }.agent-orb.catalog { background: #f59e0b; }.agent-orb.knowledge { background: #10b981; }.detail-heading small { color: $text-placeholder; }.detail-heading h3 { margin: 2px 0; font-size: 19px; }.detail-heading p { margin: 0; color: $text-secondary; font-size: 12px; }.mono { font-family: ui-monospace,monospace; font-size: 11px; }.content-card { padding: 16px 18px; border: 1px solid $border-color; border-radius: 14px; background: $surface-muted; }.content-card.response { background: color-mix(in srgb,$primary-color 5%,$surface-color); }.content-card > span,.detail-section h4 { color: $text-secondary; font-size: 11px; font-weight: 800; letter-spacing: .04em; }.content-card p { margin: 9px 0 0; line-height: 1.75; white-space: pre-wrap; }.detail-section h4 { margin: 0 0 10px; }.tool-chain { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }.tool-chain span,.attachment-list span { padding: 7px 10px; border: 1px solid $border-color; border-radius: 9px; background: $surface-muted; font-size: 11px; }.attachment-list { display: flex; flex-wrap: wrap; gap: 8px; }.attachment-list span { display: inline-flex; align-items: center; gap: 6px; }
@media (max-width: 950px) { .filters { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 620px) { .filters { grid-template-columns: 1fr; }.pagination-row { padding: 14px; align-items: flex-start; flex-direction: column; } }
</style>
