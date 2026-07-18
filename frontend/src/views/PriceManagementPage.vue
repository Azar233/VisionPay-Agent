<template>
  <div class="price-management-page">
    <div class="page-header">
      <div>
        <h1 class="vp-page-title">价目表管理</h1>
        <p class="vp-page-subtitle">选择数据集版本后，只管理该版本中已有商品的价格</p>
      </div>
    </div>

    <section class="card-container dataset-scope-panel">
      <div class="scope-copy">
        <strong><span class="required-star">*</span>数据集版本</strong>
        <span>价格按稳定 product_id 关联，同一商品在其他数据集版本中会同步使用新价格。</span>
      </div>
      <el-select
        v-model="selectedDatasetId"
        filterable
        clearable
        :loading="datasetLoading"
        placeholder="请先搜索并选择要管理的数据集版本"
        class="dataset-selector"
        @change="handleDatasetChange"
      >
        <el-option
          v-for="dataset in datasetVersions"
          :key="dataset.id"
          :label="datasetOptionLabel(dataset)"
          :value="dataset.id"
        >
          <div class="dataset-option">
            <span>{{ datasetOptionLabel(dataset) }}</span>
            <span v-if="dataset.is_current" class="vp-pill vp-pill--success">当前</span>
            <span
              v-else
              :class="['vp-pill', `vp-pill--${datasetStatusType(dataset.status)}` ]"
            >
              {{ datasetStatusText(dataset.status) }}
            </span>
          </div>
        </el-option>
      </el-select>
      <div v-if="selectedDataset" class="selected-dataset-summary">
        <span class="vp-pill vp-pill--primary">{{ selectedDataset.scene_name || `场景 #${selectedDataset.scene_id}` }}</span>
        <strong>{{ selectedDataset.version }}</strong>
        <span>{{ selectedDataset.name }}</span>
        <span class="summary-count">{{ selectedDataset.class_count }} 种商品</span>
      </div>
    </section>

    <section v-if="!selectedDatasetId" class="card-container empty-card">
      <el-empty
        description="请选择数据集版本后再管理价目表"
        :image-size="120"
      />
    </section>

    <template v-else>
      <section class="card-container table-card">
        <div class="table-toolbar">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索商品名、条码、product_id 或 product_key"
            clearable
            style="width: 380px; max-width: 100%"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #append>
              <el-button :icon="Search" @click="handleSearch" />
            </template>
          </el-input>
          <span class="scope-hint">当前仅显示所选版本的商品</span>
        </div>

        <el-table
          v-loading="loading"
          :data="paginatedPriceList"
          row-key="product_id"
          stripe
          border
          style="width: 100%"
          :default-sort="{ prop: 'class_index', order: 'ascending' }"
          @sort-change="handleSortChange"
        >
          <el-table-column prop="class_index" label="class_id" sortable="custom" width="105" />
          <el-table-column prop="product_id" label="product_id" sortable="custom" width="112" />
          <el-table-column prop="name" label="商品名称" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.name || row.display_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="class_name" label="类别名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="product_key" label="product_key" min-width="210" show-overflow-tooltip />
          <el-table-column prop="barcode" label="商品条码" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.barcode || '-' }}</template>
          </el-table-column>
          <el-table-column prop="unit_price" label="单价" sortable="custom" width="120">
            <template #default="{ row }">
              <span v-if="row.has_price" class="price-value">{{ formatPrice(row.unit_price) }}</span>
              <span v-else class="vp-pill vp-pill--warning">未配置</span>
            </template>
          </el-table-column>
          <el-table-column prop="currency" label="货币" width="80" />
          <el-table-column prop="updated_at" label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <div class="table-actions vp-table-action-safe-area">
                <el-button
                  class="row-action vp-table-action-button is-primary-action"
                  size="small"
                  :icon="Edit"
                  :aria-label="row.has_price ? '编辑价格' : '配置价格'"
                  @click="openEditDialog(row)"
                >
                  <span class="row-action-label">{{ row.has_price ? '编辑' : '配置价格' }}</span>
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <footer class="pagination-row">
          <span>共 {{ priceList.length }} 种商品，每页 {{ PAGE_SIZE }} 条</span>
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="PAGE_SIZE"
            :total="priceList.length"
            background
            layout="prev, pager, next"
          />
        </footer>
      </section>
    </template>

    <el-dialog
      v-model="dialogVisible"
      title="编辑已有商品价格"
      width="540px"
      append-to-body
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px" status-icon>
        <el-form-item label="product_id">
          <el-input :model-value="String(editingRow?.product_id ?? '')" disabled />
        </el-form-item>
        <el-form-item label="class_id">
          <el-input :model-value="String(editingRow?.class_index ?? '')" disabled />
        </el-form-item>
        <el-form-item label="SKU 英文名" prop="sku_name">
          <el-input v-model="form.sku_name" placeholder="如 apple" />
        </el-form-item>
        <el-form-item label="商品中文名" prop="name">
          <el-input v-model="form.name" placeholder="如 红富士苹果" />
        </el-form-item>
        <el-form-item label="商品条码" prop="barcode">
          <el-input v-model="form.barcode" placeholder="如 6901234567890" />
        </el-form-item>
        <el-form-item label="单价" prop="unit_price" required>
          <el-input-number
            v-model="form.unit_price"
            :min="0"
            :precision="2"
            :step="0.01"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="货币" prop="currency" required>
          <el-input v-model="form.currency" placeholder="CNY" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Search } from '@element-plus/icons-vue'
import { getDatasetVersionsApi } from '@/api/datasets'
import { getDetectionModelVersionsApi } from '@/api/training'
import { getPricesApi, updatePriceApi } from '@/api/prices'

const PAGE_SIZE = 10
const datasetLoading = ref(false)
const loading = ref(false)
const submitting = ref(false)
const datasetVersions = ref([])
const selectedDatasetId = ref(null)
const priceList = ref([])
const searchKeyword = ref('')
const currentPage = ref(1)
const sortState = ref({ prop: 'class_index', order: 'ascending' })
const dialogVisible = ref(false)
const editingRow = ref(null)
const formRef = ref(null)
const form = ref(emptyForm())

const formRules = {
  unit_price: [{ required: true, type: 'number', message: '请输入单价', trigger: ['blur', 'change'] }],
  currency: [{ required: true, whitespace: true, message: '请输入货币', trigger: ['blur', 'change'] }],
}

const selectedDataset = computed(() => (
  datasetVersions.value.find((item) => item.id === selectedDatasetId.value) || null
))

const sortedPriceList = computed(() => {
  const { prop, order } = sortState.value
  if (!prop || !order) return priceList.value
  const direction = order === 'descending' ? -1 : 1
  return [...priceList.value].sort((left, right) => {
    const leftValue = Number(left[prop] ?? -1)
    const rightValue = Number(right[prop] ?? -1)
    return (leftValue - rightValue) * direction
  })
})

const paginatedPriceList = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return sortedPriceList.value.slice(start, start + PAGE_SIZE)
})

function emptyForm() {
  return { sku_name: '', name: '', barcode: '', unit_price: null, currency: 'CNY' }
}

function datasetOptionLabel(dataset) {
  const scene = dataset.scene_name || `场景 #${dataset.scene_id}`
  return `${scene} · ${dataset.version} · ${dataset.name}`
}

function datasetStatusText(status) {
  return {
    draft: '草稿',
    pending_train: '待训练',
    training: '训练中',
    published: '已发布',
    archived: '已归档',
  }[status] || status
}

function datasetStatusType(status) {
  return {
    draft: 'warning',
    pending_train: 'primary',
    training: 'warning',
    published: 'success',
    archived: 'info',
  }[status] || 'info'
}

function formatPrice(value) {
  return value === undefined || value === null ? '-' : `¥ ${Number(value).toFixed(2)}`
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

async function fetchDatasetVersions() {
  datasetLoading.value = true
  try {
    const response = await getDatasetVersionsApi({ limit: 500 })
    datasetVersions.value = response.items || []
  } finally {
    datasetLoading.value = false
  }
}

async function fetchPrices() {
  if (!selectedDatasetId.value) {
    priceList.value = []
    return
  }
  loading.value = true
  try {
    priceList.value = await getPricesApi(selectedDatasetId.value, searchKeyword.value)
    const lastPage = Math.max(1, Math.ceil(priceList.value.length / PAGE_SIZE))
    currentPage.value = Math.min(currentPage.value, lastPage)
  } catch {
    priceList.value = []
    currentPage.value = 1
  } finally {
    loading.value = false
  }
}

function handleDatasetChange() {
  searchKeyword.value = ''
  currentPage.value = 1
  priceList.value = []
  if (selectedDatasetId.value) fetchPrices()
}

function handleSearch() {
  currentPage.value = 1
  fetchPrices()
}

function handleSortChange({ prop, order }) {
  sortState.value = { prop, order }
  currentPage.value = 1
}

function resetForm() {
  editingRow.value = null
  form.value = emptyForm()
  formRef.value?.resetFields()
}

function openEditDialog(row) {
  if (!selectedDatasetId.value) return
  editingRow.value = row
  form.value = {
    sku_name: row.sku_name || '',
    name: row.name || row.display_name || '',
    barcode: row.barcode || '',
    unit_price: row.unit_price,
    currency: row.currency || 'CNY',
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !selectedDatasetId.value || !editingRow.value) return
  submitting.value = true
  try {
    await updatePriceApi(selectedDatasetId.value, editingRow.value.product_id, {
      sku_name: form.value.sku_name.trim() || null,
      name: form.value.name.trim() || null,
      barcode: form.value.barcode.trim() || null,
      unit_price: form.value.unit_price,
      currency: form.value.currency.trim(),
    })
    ElMessage.success('商品价格已更新')
    dialogVisible.value = false
    await fetchPrices()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await fetchDatasetVersions()
  if (!selectedDatasetId.value) {
    await autoSelectDefaultModelDataset()
  }
})

async function autoSelectDefaultModelDataset() {
  try {
    const response = await getDetectionModelVersionsApi()
    const defaultModel = (response.items || []).find((item) => item.is_default)
    if (defaultModel?.dataset_version_id) {
      selectedDatasetId.value = defaultModel.dataset_version_id
      await fetchPrices()
      return
    }
  } catch {
    // ignore and fall back to current dataset
  }
  const currentDataset = datasetVersions.value.find((item) => item.is_current)
  if (currentDataset) {
    selectedDatasetId.value = currentDataset.id
    await fetchPrices()
  }
}
</script>

<style lang="scss" scoped>
.price-management-page {
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
}

.dataset-scope-panel {
  margin-bottom: 16px;
}

.scope-copy {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
  color: $text-secondary;
  font-size: 13px;

  strong { color: $text-primary; font-size: 14px; }
}

.required-star { margin-right: 3px; color: $danger-color; }
.dataset-selector { width: min(720px, 100%); }
.dataset-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-right: 8px;
}
.selected-dataset-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  color: $text-secondary;
  font-size: 13px;

  strong { color: $text-primary; font-size: 14px; }
  .summary-count { color: $text-secondary; }
}

.empty-card {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.table-card {
  padding: 20px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.scope-hint { color: $text-secondary; font-size: 13px; }
.table-actions { display: flex; align-items: center; justify-content: center; }
.row-action {
  min-width: 88px;
  max-width: 100%;
  margin-left: 0;
  padding-inline: 12px;
  border-radius: $border-radius-sm;
  font-weight: 500;

  :deep(.el-icon) { flex: 0 0 auto; }
}
.edit-action {
  color: $primary-color;
  border-color: $primary-color;
  background: $primary-soft;

  &:hover,
  &:focus-visible {
    color: $primary-hover;
    border-color: $primary-hover;
    background: $primary-soft;
  }
}

.price-value { color: $text-primary; font-weight: 600; }

:deep(.el-table) {
  --el-table-header-bg-color: #{$surface-color};
  --el-table-header-text-color: #{$text-secondary};

  th.el-table__cell {
    font-weight: 600;
    background: $surface-color;
    border-bottom-color: $border-color;
  }

  td.el-table__cell {
    color: $text-regular;
    border-bottom-color: $border-color;
  }

  tr:hover > td.el-table__cell,
  .el-table__body tr.hover-row > td.el-table__cell {
    background: $surface-muted;
  }
}

.pagination-row {
  min-height: 64px;
  padding: 12px 4px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  > span { color: $text-secondary; font-size: 12px; }
}

@media (max-width: 720px) {
  .page-header { margin-bottom: 16px; }
  .scope-copy,
  .selected-dataset-summary,
  .pagination-row { align-items: flex-start; flex-direction: column; }

  .row-action {
    width: 32px;
    min-width: 32px;
    height: 32px;
    min-height: 32px;
    padding: 0;
  }

  .row-action-label { display: none; }
}
</style>
