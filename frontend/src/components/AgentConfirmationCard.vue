<template>
  <section class="confirmation-card">
    <div class="confirmation-heading">
      <div class="risk-mark" :class="operation.risk_level?.toLowerCase()">
        {{ operation.risk_level || 'R2' }}
      </div>
      <div class="heading-copy">
        <span>安全确认</span>
        <strong>{{ operation.impact?.title || operation.action }}</strong>
      </div>
      <el-tag :type="statusType" effect="light" round>{{ statusText }}</el-tag>
    </div>

    <p class="summary">{{ operation.impact?.summary }}</p>

    <div v-if="targetEntries.length" class="target-strip">
      <span v-for="([key, value]) in targetEntries.slice(0, 4)" :key="key">
        <small>{{ keyText(key) }}</small><b>{{ valueText(value) }}</b>
      </span>
    </div>

    <dl v-if="changeEntries.length" class="changes">
      <template v-for="([key, value]) in changeEntries" :key="key">
        <dt>{{ keyText(key) }}</dt><dd>{{ valueText(value) }}</dd>
      </template>
    </dl>

    <div v-if="operation.impact?.warnings?.length" class="warnings">
      <el-icon><WarningFilled /></el-icon>
      <ul><li v-for="warning in operation.impact.warnings" :key="warning">{{ warning }}</li></ul>
    </div>

    <div v-if="operation.status === 'pending'" class="actions">
      <el-button
        :type="operation.risk_level === 'R3' ? 'danger' : 'primary'"
        :loading="working"
        @click="confirmOperation"
      >
        {{ operation.risk_level === 'R3' ? '确认高风险操作' : '确认执行' }}
      </el-button>
      <el-button :disabled="working" @click="cancelOperation">取消</el-button>
      <small>令牌仅使用一次，{{ expiresText }}</small>
    </div>

    <div v-if="operation.status === 'completed'" class="completed-state">
      <el-icon><CircleCheckFilled /></el-icon><span>操作已执行完成</span>
      <small v-if="operation.replayed">本次为幂等结果重放，没有重复执行</small>
    </div>
    <pre v-if="operation.result" class="result">{{ valueText(operation.result) }}</pre>
    <p v-if="operation.error_message" class="error">{{ operation.error_message }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  cancelAgentOperationApi,
  confirmAgentOperationApi,
  getAgentOperationApi,
  rotateAgentOperationTokenApi,
} from '@/api/agentOperations'

const props = defineProps({ operation: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const working = ref(false)

const changeEntries = computed(() => Object.entries(props.operation.impact?.changes || {}))
const targetEntries = computed(() => Object.entries(props.operation.impact?.target || {}))
const statusText = computed(() => ({
  pending: '等待确认', executing: '执行中', completed: '已完成', failed: '执行失败',
  cancelled: '已取消', expired: '已过期',
})[props.operation.status] || props.operation.status)
const statusType = computed(() => ({
  pending: 'warning', executing: 'primary', completed: 'success', failed: 'danger',
  cancelled: 'info', expired: 'info',
})[props.operation.status] || 'info')
const expiresText = computed(() => {
  if (!props.operation.token_expires_at) return '确认时自动获取一次性令牌'
  const date = new Date(props.operation.token_expires_at)
  return Number.isNaN(date.getTime()) ? '令牌短时有效' : `有效至 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
})

function keyText(key) {
  return ({
    dataset_id: '数据集 ID', dataset_version_id: '数据集 ID', version: '版本', name: '名称',
    product_id: '商品 ID', product_key: '商品标识', class_name: '类别', status: '状态变化',
    images: '图片数', annotations: '标注数', classes: '类别数', training_tasks: '训练引用',
    model_versions: '模型引用', old_price: '原价', new_price: '新价', old_currency: '原币种',
    new_currency: '新币种', old_model_version: '原模型', new_model_version: '新模型',
    affected_images: '受影响图片', annotations_deleted: '删除标注',
    mixed_scene_images_retained: '保留多商品场景', classes_reindexed: '重排类别',
    epochs: '训练轮数', batch_size: '批次大小', img_size: '图片尺寸', device: '训练设备',
    model_name: '模型', optimizer: '优化器', lr0: '学习率', permanent_delete: '永久删除',
  })[key] || key
}
function valueText(value) {
  if (value === null || value === undefined) return '无'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}
function executionKey() {
  if (!props.operation.executionKey) {
    props.operation.executionKey = `confirm-${props.operation.operation_uuid}-${crypto.randomUUID?.() || Date.now()}`
  }
  return props.operation.executionKey
}
async function syncOperation() {
  try {
    const current = await getAgentOperationApi(props.operation.operation_uuid)
    Object.assign(props.operation, current)
  } catch { /* 会话本身仍可显示持久化快照 */ }
}
async function confirmOperation() {
  if (working.value || props.operation.status !== 'pending') return
  working.value = true
  try {
    let token = props.operation.confirmation_token
    if (!token) {
      const refreshed = await rotateAgentOperationTokenApi(props.operation.operation_uuid)
      token = refreshed.confirmation_token
      Object.assign(props.operation, refreshed)
    }
    const result = await confirmAgentOperationApi(
      props.operation.operation_uuid,
      token,
      executionKey(),
    )
    Object.assign(props.operation, result, { confirmation_token: undefined })
    ElMessage.success(result.replayed ? '已返回首次执行结果，没有重复操作' : '操作执行成功')
    emit('changed', result)
  } catch (error) {
    props.operation.error_message = error?.response?.data?.detail || error.message || '操作执行失败'
    await syncOperation()
  } finally {
    working.value = false
  }
}
async function cancelOperation() {
  if (working.value || props.operation.status !== 'pending') return
  working.value = true
  try {
    const result = await cancelAgentOperationApi(props.operation.operation_uuid)
    Object.assign(props.operation, result, { confirmation_token: undefined })
    ElMessage.info('已取消待确认操作')
    emit('changed', result)
  } catch (error) {
    props.operation.error_message = error?.response?.data?.detail || error.message || '取消失败'
  } finally {
    working.value = false
  }
}

onMounted(syncOperation)
</script>

<style lang="scss" scoped>
.confirmation-card { margin-top: 14px; padding: 16px; border: 1px solid rgba(245, 158, 11, .28); border-radius: 18px; background: linear-gradient(145deg, rgba(255, 251, 235, .9), rgba(255, 255, 255, .96)); box-shadow: 0 12px 30px rgba(120, 53, 15, .08); }
.confirmation-heading { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; align-items: center; gap: 10px; }.risk-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; color: #fff; background: #f59e0b; font-size: 11px; font-weight: 900; }.risk-mark.r3 { background: #ef4444; }.heading-copy { display: flex; flex-direction: column; gap: 2px; }.heading-copy span { color: #b45309; font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }.heading-copy strong { color: $text-primary; font-size: 14px; }.summary { margin: 13px 0; color: $text-secondary; font-size: 12px; line-height: 1.7; }
.target-strip { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }.target-strip span { min-width: 86px; display: flex; flex-direction: column; gap: 2px; padding: 7px 9px; border: 1px solid $border-color; border-radius: 10px; background: rgba(255, 255, 255, .8); }.target-strip small { color: $text-placeholder; font-size: 9px; }.target-strip b { overflow: hidden; color: $text-primary; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.changes { display: grid; grid-template-columns: minmax(92px, .65fr) minmax(0, 1.35fr); margin: 0; overflow: hidden; border: 1px solid $border-color; border-radius: 12px; background: rgba(255, 255, 255, .72); }.changes dt, .changes dd { margin: 0; padding: 7px 10px; border-bottom: 1px solid $border-color; font-size: 10px; }.changes dt { color: $text-secondary; background: $surface-muted; }.changes dd { color: $text-primary; overflow-wrap: anywhere; white-space: pre-wrap; }
.warnings { display: flex; align-items: flex-start; gap: 8px; margin-top: 10px; padding: 9px 10px; border-radius: 10px; color: #b45309; background: rgba(245, 158, 11, .09); font-size: 10px; }.warnings .el-icon { margin-top: 2px; flex: 0 0 auto; }.warnings ul { margin: 0; padding-left: 14px; line-height: 1.6; }.actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 13px; }.actions small { margin-left: auto; color: $text-placeholder; font-size: 9px; }.completed-state { display: flex; align-items: center; gap: 7px; margin-top: 12px; color: $success-color; font-size: 11px; font-weight: 800; }.completed-state small { margin-left: auto; color: $text-placeholder; font-weight: 500; }.result { max-height: 170px; margin: 10px 0 0; padding: 10px; overflow: auto; border-radius: 10px; color: $text-secondary; background: $surface-muted; font-size: 9px; white-space: pre-wrap; }.error { margin: 10px 0 0; color: $danger-color; font-size: 11px; }
@media (max-width: 640px) { .confirmation-heading { grid-template-columns: 38px 1fr; }.confirmation-heading .el-tag { grid-column: 2; justify-self: start; }.actions small { width: 100%; margin-left: 0; } }
:global(html.dark .confirmation-card) { background: linear-gradient(145deg,rgba(80,55,15,.42),rgba(44,44,46,.96)); border-color: rgba(255,159,10,.28); box-shadow: 0 14px 34px rgba(0,0,0,.28); }
:global(html.dark .confirmation-card .heading-copy strong),
:global(html.dark .confirmation-card .target-strip b),
:global(html.dark .confirmation-card .changes dd) { color: #f5f5f7; }
:global(html.dark .confirmation-card .target-strip span),
:global(html.dark .confirmation-card .changes) { background: rgba(44,44,46,.8); border-color: rgba(255,255,255,.1); }
:global(html.dark .confirmation-card .changes dt),
:global(html.dark .confirmation-card .changes dd) { border-color: rgba(255,255,255,.08); }
:global(html.dark .confirmation-card .changes dt) { background: rgba(58,58,60,.82); }
:global(html.dark .confirmation-card .warnings) { color: #ffd60a; background: rgba(255,159,10,.1); }
:global(html.dark .confirmation-card .result) { color: #d1d1d6; background: #1c1c1e; }
</style>
