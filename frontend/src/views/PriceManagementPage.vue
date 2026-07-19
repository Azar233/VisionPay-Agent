<template>
  <div class="price-management-page">
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
        <span v-if="isCatalogOnly" class="catalog-only-note">导入的可用模型无法查看图片</span>
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
            style="width: 540px; max-width: 100%"
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
          class="price-table"
          row-key="product_id"
          :default-sort="{ prop: 'class_index', order: 'ascending' }"
          empty-text="当前数据集版本暂无商品"
          @sort-change="handleSortChange"
        >
          <el-table-column prop="name" label="商品信息" min-width="210">
            <template #default="{ row }">
              <div class="product-identity">
                <strong :title="row.name || row.display_name || '-'">{{ row.name || row.display_name || '-' }}</strong>
                <span :title="row.class_name">{{ row.class_name || '未命名类别' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="class_index" label="class_id" sortable="custom" min-width="120">
            <template #default="{ row }">{{ row.class_index }}</template>
          </el-table-column>
          <el-table-column prop="product_id" label="product_id" min-width="110" />
          <el-table-column prop="product_key" label="product_key" min-width="190" show-overflow-tooltip>
            <template #default="{ row }">{{ row.product_key || '-' }}</template>
          </el-table-column>
          <el-table-column prop="barcode" label="商品条码" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.barcode || '-' }}</template>
          </el-table-column>
          <el-table-column prop="unit_price" label="销售价格" sortable="custom" min-width="130" align="right">
            <template #default="{ row }">
              <div v-if="row.has_price" class="price-cell">
                <strong>{{ formatPrice(row.unit_price) }}</strong>
                <span>{{ row.currency || 'CNY' }}</span>
              </div>
              <span v-else class="vp-pill vp-pill--warning">未配置</span>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="170">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" :width="isCatalogOnly ? 112 : 190" fixed="right" align="center">
            <template #default="{ row }">
              <div class="table-actions vp-table-action-safe-area">
                <el-button
                  v-if="!isCatalogOnly"
                  class="row-action image-action"
                  size="small"
                  :icon="Picture"
                  aria-label="查看训练集图片"
                  @click="openSamplePreview(row)"
                >
                  <span class="row-action-label">查看图片</span>
                </el-button>
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
          <span>共 {{ priceList.length }} 种商品</span>
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50]"
            :total="priceList.length"
            layout="sizes, prev, pager, next"
            @size-change="handleSizeChange"
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

    <el-dialog
      v-model="samplePreviewVisible"
      :title="`${samplePreviewProduct?.name || samplePreviewProduct?.display_name || '商品'} · 全部训练集图片`"
      width="min(1120px, 94vw)"
      append-to-body
      destroy-on-close
      @closed="closeSamplePreview"
    >
      <div v-loading="samplePreviewLoading" class="sample-preview">
        <el-empty
          v-if="!samplePreviewLoading && !samplePreviewItems.length"
          description="该商品暂无关联的训练集图片"
          :image-size="96"
        />
        <div v-else class="sample-preview-grid">
          <article v-for="item in samplePreviewItems" :key="item.id" class="sample-preview-card">
            <div v-loading="item.loading" class="sample-preview-image">
              <img
                v-if="item.url"
                :src="item.url"
                :alt="`${samplePreviewProduct?.name || '商品'} · ${item.filename}`"
              >
              <span v-else-if="item.error">图片加载失败</span>
            </div>
            <div class="sample-preview-card-meta">
              <span :title="item.filename">{{ item.filename }}</span>
              <span :class="['dataset-split', `dataset-split--${item.split}`]">
                {{ splitLabel(item.split) }}
              </span>
            </div>
          </article>
        </div>
      </div>
      <template #footer>
        <div class="sample-preview-footer">
          <span class="sample-preview-meta">
            product_id {{ samplePreviewProduct?.product_id }} ·
            已加载 {{ samplePreviewLoadedCount }} / {{ samplePreviewItems.length }} 张
          </span>
          <el-button @click="samplePreviewVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Picture, Search } from '@element-plus/icons-vue'
import {
  getDatasetProductImageApi,
  getDatasetProductImagesApi,
  getDatasetVersionsApi,
} from '@/api/datasets'
import { getDetectionModelVersionsApi } from '@/api/training'
import { getPricesApi, updatePriceApi } from '@/api/prices'

const datasetLoading = ref(false)
const loading = ref(false)
const submitting = ref(false)
const datasetVersions = ref([])
const selectedDatasetId = ref(null)
const priceList = ref([])
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const sortState = ref({ prop: 'class_index', order: 'ascending' })
const dialogVisible = ref(false)
const editingRow = ref(null)
const samplePreviewVisible = ref(false)
const samplePreviewLoading = ref(false)
const samplePreviewItems = ref([])
const samplePreviewProduct = ref(null)
const samplePreviewRequestId = ref(0)
const formRef = ref(null)
const form = ref(emptyForm())

const formRules = {
  unit_price: [{ required: true, type: 'number', message: '请输入单价', trigger: ['blur', 'change'] }],
  currency: [{ required: true, whitespace: true, message: '请输入货币', trigger: ['blur', 'change'] }],
}

const selectedDataset = computed(() => (
  datasetVersions.value.find((item) => item.id === selectedDatasetId.value) || null
))
const isCatalogOnly = computed(() => Boolean(selectedDataset.value?.extra_metadata?.catalog_only))
const samplePreviewLoadedCount = computed(() => (
  samplePreviewItems.value.filter((item) => Boolean(item.url)).length
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
  const start = (currentPage.value - 1) * pageSize.value
  return sortedPriceList.value.slice(start, start + pageSize.value)
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
    const lastPage = Math.max(1, Math.ceil(priceList.value.length / pageSize.value))
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

function handleSizeChange() {
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

function splitLabel(split) {
  return { train: '训练集', val: '验证集', test: '测试集' }[split] || split
}

function revokeSamplePreviewUrls() {
  samplePreviewItems.value.forEach((item) => {
    if (item.url) URL.revokeObjectURL(item.url)
  })
  samplePreviewItems.value = []
}

async function loadPreviewImage(item, datasetId, productId, requestId) {
  try {
    const imageBlob = await getDatasetProductImageApi(datasetId, productId, item.id)
    if (requestId !== samplePreviewRequestId.value || !samplePreviewVisible.value) return
    item.url = URL.createObjectURL(imageBlob)
  } catch {
    if (requestId === samplePreviewRequestId.value) item.error = true
  } finally {
    if (requestId === samplePreviewRequestId.value) item.loading = false
  }
}

async function loadPreviewImages(items, datasetId, productId, requestId) {
  const queue = [...items]
  const worker = async () => {
    while (queue.length && requestId === samplePreviewRequestId.value) {
      const item = queue.shift()
      await loadPreviewImage(item, datasetId, productId, requestId)
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker))
}

async function openSamplePreview(row) {
  if (!selectedDatasetId.value || isCatalogOnly.value) return
  const requestId = ++samplePreviewRequestId.value
  revokeSamplePreviewUrls()
  samplePreviewProduct.value = row
  samplePreviewLoading.value = true
  samplePreviewVisible.value = true
  try {
    const response = await getDatasetProductImagesApi(
      selectedDatasetId.value,
      row.product_id,
    )
    if (requestId !== samplePreviewRequestId.value || !samplePreviewVisible.value) return
    samplePreviewItems.value = (response.items || []).map((item) => ({
      ...item,
      url: '',
      loading: true,
      error: false,
    }))
    samplePreviewLoading.value = false
    if (!samplePreviewItems.value.length) return
    void loadPreviewImages(
      samplePreviewItems.value,
      selectedDatasetId.value,
      row.product_id,
      requestId,
    )
  } catch (error) {
    if (requestId !== samplePreviewRequestId.value) return
    const detail = error.response?.data?.detail || error.response?.data?.message
    ElMessage.warning(detail || '无法读取该商品的训练集图片')
    samplePreviewVisible.value = false
    samplePreviewProduct.value = null
  } finally {
    if (requestId === samplePreviewRequestId.value) samplePreviewLoading.value = false
  }
}

function closeSamplePreview() {
  samplePreviewRequestId.value += 1
  samplePreviewLoading.value = false
  revokeSamplePreviewUrls()
  samplePreviewProduct.value = null
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

onBeforeUnmount(revokeSamplePreviewUrls)

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
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 100%;
  padding: 24px;
  color: $text-primary;
  background: $bg-color;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0 14px;

  .vp-kicker {
    margin-bottom: 6px;
  }
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

.catalog-only-note {
  padding-left: 10px;
  color: $warning-color;
  font-size: 13px;
  font-weight: 600;
  border-left: 1px solid $border-color;
}

.empty-card {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.table-card {
  padding: 0;
  overflow: hidden;
  border-radius: 16px;
}

.table-toolbar {
  min-height: 58px;
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid $border-color;
  background: $surface-color;
}

.scope-hint { color: $text-secondary; font-size: 13px; }
.table-actions { display: flex; align-items: center; justify-content: center; gap: 8px; }
.row-action {
  min-width: 78px;
  max-width: 100%;
  margin-left: 0;
  padding-inline: 12px;
  border-radius: $border-radius-sm;
  font-weight: 500;

  :deep(.el-icon) { flex: 0 0 auto; }
}
.image-action {
  color: $text-regular;
  border-color: $border-color;
  background: $surface-color;

  &:hover,
  &:focus-visible {
    color: $primary-color;
    border-color: $primary-color;
    background: $primary-soft;
  }
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

.product-identity,
.price-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.product-identity strong {
  overflow: hidden;
  color: $text-primary;
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-identity span,
.price-cell span {
  color: $text-secondary;
  font-size: 12.5px;
}

.price-cell { align-items: flex-end; }
.price-cell strong { color: $text-primary; font-size: 15px; font-weight: 700; }

:deep(.el-table) {
  --el-table-header-bg-color: #{$surface-muted};
  --el-table-header-text-color: #{$text-secondary};
  --el-table-row-hover-bg-color: #{$surface-muted};

  .cell {
    padding: 0 14px;
    font-size: 13px;
    line-height: 1.35;
  }

  th.el-table__cell {
    height: 44px;
    padding: 0;
    font-weight: 600;
    background: $surface-muted;
    border-bottom-color: $border-color;
  }

  td.el-table__cell {
    height: 54px;
    padding: 0;
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
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid $border-color;

  > span { color: $text-secondary; font-size: 12px; }
}

.sample-preview {
  min-height: 320px;
  max-height: 68vh;
  overflow: auto;
  padding: 14px;
  border: 1px solid $border-color;
  border-radius: 12px;
  background: $surface-muted;
}

.sample-preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.sample-preview-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: 11px;
  background: $surface-color;
}

.sample-preview-image {
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: $bg-color;

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  span {
    color: $text-placeholder;
    font-size: 13px;
  }
}

.sample-preview-card-meta {
  min-height: 42px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;

  > span:first-child {
    min-width: 0;
    overflow: hidden;
    color: $text-secondary;
    font-size: 12.5px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.dataset-split {
  flex: 0 0 auto;
  padding: 3px 7px;
  color: $text-secondary;
  font-size: 11px;
  font-weight: 650;
  border-radius: 999px;
  background: $surface-muted;

  &--train { color: $primary-color; background: $primary-soft; }
  &--val { color: $success-color; background: var(--vp-success-bg); }
  &--test { color: $warning-color; background: var(--vp-warning-bg); }
}

.sample-preview-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.sample-preview-meta {
  color: $text-secondary;
  font-size: 13px;
}

@media (max-width: 760px) {
  .price-management-page { padding: 16px; }
  .page-header { align-items: flex-start; flex-direction: column; }
  .scope-copy,
  .selected-dataset-summary,
  .pagination-row { align-items: flex-start; flex-direction: column; }

  .pagination-row { padding: 14px; }

  .sample-preview { padding: 10px; }
  .sample-preview-grid { grid-template-columns: 1fr; gap: 10px; }
  .sample-preview-footer { align-items: flex-start; flex-direction: column; }

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
