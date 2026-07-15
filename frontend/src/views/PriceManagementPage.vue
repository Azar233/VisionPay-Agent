<template>
  <div class="price-management-page">
    <el-card shadow="never" class="page-card">
      <div class="page-header">
        <div>
          <h2>价目表管理</h2>
          <p class="subtitle">维护商品 SKU、名称与单价，修改后结算端即时生效</p>
        </div>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">
          新增商品
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="priceList"
        stripe
        border
        style="width: 100%"
        :default-sort="{ prop: 'category_id', order: 'ascending' }"
      >
        <el-table-column prop="category_id" label="类别 ID" sortable width="110" />
        <el-table-column prop="sku_name" label="SKU 英文名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="name" label="商品中文名" min-width="160" show-overflow-tooltip />
        <el-table-column prop="barcode" label="条码" min-width="140" show-overflow-tooltip />
        <el-table-column prop="unit_price" label="单价" sortable width="120">
          <template #default="{ row }">
            {{ formatPrice(row.unit_price) }}
          </template>
        </el-table-column>
        <el-table-column prop="currency" label="货币" width="90" />
        <el-table-column prop="updated_at" label="更新时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="176" fixed="right" align="center">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button class="row-action edit-action" size="small" :icon="Edit" @click="openEditDialog(row)">编辑</el-button>
              <el-button class="row-action delete-action" size="small" :icon="Delete" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑商品' : '新增商品'"
      width="520px"
      append-to-body
      destroy-on-close
      @closed="resetForm"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="110px"
        status-icon
      >
        <el-form-item label="类别 ID" prop="category_id">
          <el-input
            v-if="isEdit"
            :model-value="String(editingCategoryId ?? '')"
            disabled
          />
          <el-input-number
            v-else
            v-model="form.category_id"
            :min="1"
            :max="200"
            controls-position="right"
            style="width: 100%"
          />
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
        <el-form-item label="单价" prop="unit_price">
          <el-input-number
            v-model="form.unit_price"
            :min="0"
            :precision="2"
            :step="0.01"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="货币" prop="currency">
          <el-input v-model="form.currency" placeholder="CNY" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus } from '@element-plus/icons-vue'
import {
  getPricesApi,
  createPriceApi,
  updatePriceApi,
  deletePriceApi,
} from '@/api/prices'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingCategoryId = ref(null)
const priceList = ref([])

const formRef = ref(null)
const form = ref({
  category_id: 1,
  sku_name: '',
  name: '',
  barcode: '',
  unit_price: 0,
  currency: 'CNY',
})

const formRules = {
  category_id: [{ required: true, message: '请输入类别 ID', trigger: 'blur' }],
  unit_price: [{ required: true, message: '请输入单价', trigger: 'blur' }],
  currency: [{ required: true, message: '请输入货币', trigger: 'blur' }],
}

function formatPrice(value) {
  if (value === undefined || value === null) return '-'
  return `¥ ${Number(value).toFixed(2)}`
}

function formatTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

async function fetchPrices() {
  loading.value = true
  try {
    priceList.value = await getPricesApi()
  } catch {
    priceList.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingCategoryId.value = null
  form.value = {
    category_id: 1,
    sku_name: '',
    name: '',
    barcode: '',
    unit_price: 0,
    currency: 'CNY',
  }
  isEdit.value = false
  formRef.value?.resetFields()
}

function openCreateDialog() {
  isEdit.value = false
  editingCategoryId.value = null
  form.value = {
    category_id: 1,
    sku_name: '',
    name: '',
    barcode: '',
    unit_price: 0,
    currency: 'CNY',
  }
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  editingCategoryId.value = Number(row.category_id)
  form.value = {
    category_id: row.category_id,
    sku_name: row.sku_name || '',
    name: row.name || '',
    barcode: row.barcode || '',
    unit_price: row.unit_price,
    currency: row.currency || 'CNY',
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const payload = {
      sku_name: form.value.sku_name || null,
      name: form.value.name || null,
      barcode: form.value.barcode || null,
      unit_price: form.value.unit_price,
      currency: form.value.currency,
    }

    if (isEdit.value) {
      await updatePriceApi(editingCategoryId.value, payload)
      ElMessage.success('商品更新成功')
    } else {
      await createPriceApi({ category_id: form.value.category_id, ...payload })
      ElMessage.success('商品创建成功')
    }

    dialogVisible.value = false
    await fetchPrices()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除类别 ID 为 ${row.category_id} 的商品吗？删除后结算端将无法计价该商品。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  try {
    await deletePriceApi(row.category_id)
    ElMessage.success('删除成功')
    await fetchPrices()
  } catch {
    // 错误已由 request 拦截器提示
  }
}

onMounted(() => {
  fetchPrices()
})
</script>

<style lang="scss" scoped>
.price-management-page {
  padding: 20px;

  .page-card {
    border-radius: 12px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 20px;

    h2 {
      margin: 0 0 6px;
      font-size: 20px;
      font-weight: 600;
    }

    .subtitle {
      margin: 0;
      color: #6b7280;
      font-size: 13px;
    }
  }

  .table-actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;

    .row-action {
      min-width: 68px;
      margin-left: 0;
      border-radius: 8px;
      font-weight: 500;
      transition: color .2s ease, border-color .2s ease, background-color .2s ease, box-shadow .2s ease;
    }

    .edit-action {
      color: #0969da;
      border-color: #b9d7f8;
      background: #f2f8ff;

      &:hover,
      &:focus-visible {
        color: #fff;
        border-color: #0969da;
        background: #0969da;
        box-shadow: 0 4px 12px rgba(9, 105, 218, .18);
      }
    }

    .delete-action {
      color: #cf3f4f;
      border-color: #f0c4ca;
      background: #fff6f7;

      &:hover,
      &:focus-visible {
        color: #fff;
        border-color: #cf3f4f;
        background: #cf3f4f;
        box-shadow: 0 4px 12px rgba(207, 63, 79, .16);
      }
    }
  }
}
</style>
