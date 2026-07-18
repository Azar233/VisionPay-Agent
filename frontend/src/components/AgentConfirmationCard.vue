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
      <span
        class="vp-pill"
        :class="{
          'vp-pill--warning': operation.status === 'pending',
          'vp-pill--primary': operation.status === 'executing',
          'vp-pill--success': operation.status === 'completed',
          'vp-pill--danger': operation.status === 'failed',
        }"
      >{{ statusText }}</span>
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
import { beginVisionPetTask, getBackendErrorMessage } from '@/utils/visionPet'
import {
  cancelAgentOperationApi,
  confirmAgentOperationApi,
  getAgentOperationApi,
  rotateAgentOperationTokenApi,
} from '@/api/agentOperations'

const props = defineProps({ operation: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const working = ref(false)
const PROGRESS_ACTIONS = new Set(['dataset.derive', 'dataset.delete_draft', 'dataset.delete_product'])
const waitForProgressPoll = (duration = 120) => new Promise((resolve) => window.setTimeout(resolve, duration))

function compactProgressHistory(history, maxItems = 5) {
  if (history.length <= maxItems) return history
  return Array.from({ length: maxItems }, (_, index) => (
    history[Math.round(index * (history.length - 1) / (maxItems - 1))]
  ))
}

async function replayProgressHistory(petTask, taskProgress, lastDisplayedProgress) {
  const unseen = (taskProgress?.history || []).filter((item) => (
    Number.isFinite(Number(item.progress)) && Number(item.progress) > lastDisplayedProgress
  ))
  let latest = lastDisplayedProgress
  for (const item of compactProgressHistory(unseen)) {
    latest = Number(item.progress)
    petTask.update({
      message: `${props.operation.impact?.title || '数据集操作'}：${item.message || '正在处理'}`,
      progress: latest,
    })
    await waitForProgressPoll(90)
  }
  return latest
}

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
  // 该操作可能已在待确认弹窗等其他入口被处理，先同步最新状态再决定是否继续，
  // 避免对已完成的操作重复刷新令牌而报“只有待确认操作可以刷新令牌”。
  await syncOperation()
  if (props.operation.status !== 'pending') {
    working.value = false
    return
  }
  const tracksProgress = PROGRESS_ACTIONS.has(props.operation.action)
  const petTask = beginVisionPetTask({
    id: `agent-operation-${props.operation.operation_uuid}`,
    message: `${props.operation.impact?.title || '待确认操作'}：正在确认执行`,
    progress: tracksProgress ? 0 : null,
    showProgress: tracksProgress,
  })
  try {
    let token = props.operation.confirmation_token
    if (!token) {
      const refreshed = await rotateAgentOperationTokenApi(
        props.operation.operation_uuid,
        { skipPetError: true },
      )
      token = refreshed.confirmation_token
      Object.assign(props.operation, refreshed)
    }
    let result
    let confirmationError
    let confirmationSettled = false
    let lastDisplayedProgress = 0
    confirmAgentOperationApi(
      props.operation.operation_uuid,
      token,
      executionKey(),
      { skipPetError: true },
    )
      .then((value) => { result = value })
      .catch((error) => { confirmationError = error })
      .finally(() => { confirmationSettled = true })

    while (tracksProgress && !confirmationSettled) {
      await waitForProgressPoll()
      if (confirmationSettled) break
      const current = await getAgentOperationApi(
        props.operation.operation_uuid,
        { skipGlobalError: true },
      ).catch(() => null)
      const progress = current?.task_progress
      if (!progress) continue
      Object.assign(props.operation, current)
      petTask.update({
        message: `${props.operation.impact?.title || '数据集操作'}：${progress.message || '正在处理'}`,
        progress: progress.progress,
      })
      lastDisplayedProgress = Math.max(lastDisplayedProgress, Number(progress.progress || 0))
    }
    // 非进度类操作（如改价）不走进度轮询，也必须等待请求落定，
    // 否则会在响应返回前误判“操作执行未返回结果”。
    while (!confirmationSettled) {
      await waitForProgressPoll(20)
    }
    if (confirmationError) throw confirmationError
    if (!result) throw new Error('操作执行未返回结果')
    Object.assign(props.operation, result, { confirmation_token: undefined })
    if (petTask && result.task_progress) {
      lastDisplayedProgress = await replayProgressHistory(
        petTask,
        result.task_progress,
        lastDisplayedProgress,
      )
    }
    petTask?.finish({
      message: `${props.operation.impact?.title || '数据集操作'}已完成`,
      progress: 100,
      duration: 4200,
    })
    ElMessage.success(result.replayed ? '已返回首次执行结果，没有重复操作' : '操作执行成功')
    emit('changed', result)
  } catch (error) {
    props.operation.error_message = getBackendErrorMessage(error, '操作执行失败')
    petTask?.finish({
      status: 'failed',
      message: `${props.operation.impact?.title || '数据集操作'}失败：${props.operation.error_message}`,
      duration: 5200,
    })
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
    props.operation.error_message = getBackendErrorMessage(error, '取消失败')
  } finally {
    working.value = false
  }
}

onMounted(syncOperation)
</script>

<style lang="scss" scoped>
.confirmation-card { margin-top: 14px; padding: 16px; background: $surface-color; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; }
.confirmation-heading { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; align-items: center; gap: 10px; }
.risk-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; color: #fff; background: $warning-color; font-size: 11px; font-weight: 900; }
.risk-mark.r3 { background: $danger-color; }
.heading-copy { display: flex; flex-direction: column; gap: 2px; }
.heading-copy span { color: $warning-color; font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.heading-copy strong { color: $text-primary; font-size: 14px; }
.summary { margin: 13px 0; color: $text-secondary; font-size: 12px; line-height: 1.7; }
.target-strip { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
.target-strip span { min-width: 86px; display: flex; flex-direction: column; gap: 2px; padding: 7px 9px; border: 1px solid $border-color; border-radius: 10px; background: $surface-muted; }
.target-strip small { color: $text-placeholder; font-size: 9px; }
.target-strip b { overflow: hidden; color: $text-primary; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.changes { display: grid; grid-template-columns: minmax(92px, .65fr) minmax(0, 1.35fr); margin: 0; overflow: hidden; border: 1px solid $border-color; border-radius: 12px; background: $surface-color; }
.changes dt, .changes dd { margin: 0; padding: 7px 10px; border-bottom: 1px solid $border-color; font-size: 10px; }
.changes dt { color: $text-secondary; background: $surface-muted; }
.changes dd { color: $text-primary; overflow-wrap: anywhere; white-space: pre-wrap; }
.warnings { display: flex; align-items: flex-start; gap: 8px; margin-top: 10px; padding: 9px 10px; border-radius: 10px; color: $warning-color; background: var(--vp-warning-bg); font-size: 10px; }
.warnings .el-icon { margin-top: 2px; flex: 0 0 auto; }
.warnings ul { margin: 0; padding-left: 14px; line-height: 1.6; }
.actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 13px; }
.actions small { margin-left: auto; color: $text-placeholder; font-size: 9px; }
.completed-state { display: flex; align-items: center; gap: 7px; margin-top: 12px; color: $success-color; font-size: 11px; font-weight: 800; }
.completed-state small { margin-left: auto; color: $text-placeholder; font-weight: 500; }
.result { max-height: 170px; margin: 10px 0 0; padding: 10px; overflow: auto; border-radius: 10px; color: $text-secondary; background: $surface-muted; font-size: 9px; white-space: pre-wrap; }
.error { margin: 10px 0 0; color: $danger-color; font-size: 11px; }
@media (max-width: 640px) { .confirmation-heading { grid-template-columns: 38px 1fr; }.confirmation-heading .vp-pill { grid-column: 2; justify-self: start; }.actions small { width: 100%; margin-left: 0; } }
</style>
