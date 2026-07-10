<template>
  <div class="training-page">
    <div class="page-header">
      <div>
        <h2>模型训练与监控</h2>
        <p>YOLOv11 训练任务、进度和指标曲线</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        新建训练任务
      </el-button>
    </div>

    <section class="panel">
      <div class="panel-header">
        <span>训练任务列表</span>
        <el-button text :icon="Refresh" :loading="loadingTasks" @click="fetchTasks">
          刷新
        </el-button>
      </div>

      <el-table
        v-loading="loadingTasks"
        :data="taskList"
        stripe
        class="task-table"
        empty-text="暂无训练任务"
      >
        <el-table-column prop="task_uuid" label="任务 ID" min-width="110" />
        <el-table-column prop="model_name" label="模型" min-width="110" />
        <el-table-column prop="device" label="设备" width="90" />
        <el-table-column label="进度" min-width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="progressStatus(row.status)"
              :stroke-width="14"
            />
          </template>
        </el-table-column>
        <el-table-column label="Epoch" width="110">
          <template #default="{ row }">
            {{ row.current_epoch || 0 }}/{{ row.epochs || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="selectTask(row)">
              监控
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              text
              @click="stopTask(row.id)"
            >
              停止
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="downloadResults(row.task_uuid)"
            >
              结果
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="selectedTask" class="panel monitor-panel">
      <div class="panel-header monitor-header">
        <div>
          <span>训练监控 - 任务 {{ selectedTask.task_uuid }}</span>
          <el-tag :type="statusType(selectedTask.status)" size="small">
            {{ statusText(selectedTask.status) }}
          </el-tag>
        </div>
        <div class="monitor-meta">
          <span>模型 {{ selectedTask.model_name }}</span>
          <span>设备 {{ selectedTask.device }}</span>
          <span>Epoch {{ selectedTask.current_epoch || 0 }}/{{ selectedTask.epochs || 0 }}</span>
        </div>
      </div>

      <div class="metric-grid">
        <div v-for="item in metricCards" :key="item.label" class="metric-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>

      <div class="chart-grid">
        <div ref="lossChartRef" class="chart"></div>
        <div ref="metricChartRef" class="chart"></div>
      </div>
    </section>

    <el-empty v-else class="empty-monitor" description="选择一个训练任务查看监控曲线" />

    <el-dialog
      v-model="showCreateDialog"
      title="新建训练任务"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form :model="trainForm" label-width="120px">
        <el-form-item label="检测场景">
          <el-input-number v-model="trainForm.scene_id" :min="1" />
        </el-form-item>

        <el-form-item label="基础模型">
          <el-select v-model="trainForm.model_name">
            <el-option label="YOLOv11n (Nano)" value="yolov11n" />
            <el-option label="YOLOv11s (Small)" value="yolov11s" />
            <el-option label="YOLOv11m (Medium)" value="yolov11m" />
            <el-option label="YOLOv11l (Large)" value="yolov11l" />
            <el-option label="YOLOv11x (XLarge)" value="yolov11x" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练轮数">
          <el-slider v-model="trainForm.epochs" :min="1" :max="100" :step="1" show-input />
        </el-form-item>

        <el-form-item label="批次大小">
          <el-input-number v-model="trainForm.batch_size" :min="1" :max="64" />
        </el-form-item>

        <el-form-item label="图像尺寸">
          <el-select v-model="trainForm.img_size">
            <el-option label="416" :value="416" />
            <el-option label="512" :value="512" />
            <el-option label="640" :value="640" />
            <el-option label="768" :value="768" />
          </el-select>
        </el-form-item>

        <el-form-item label="训练设备">
          <el-radio-group v-model="trainForm.device">
            <el-radio value="cpu">CPU</el-radio>
            <el-radio value="0">GPU 0</el-radio>
            <el-radio value="1">GPU 1</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="优化器">
          <el-select v-model="trainForm.optimizer">
            <el-option label="SGD" value="SGD" />
            <el-option label="Adam" value="Adam" />
            <el-option label="AdamW" value="AdamW" />
          </el-select>
        </el-form-item>

        <el-form-item label="初始学习率">
          <el-input-number
            v-model="trainForm.lr0"
            :min="0.0001"
            :max="0.1"
            :step="0.001"
            :precision="4"
          />
        </el-form-item>

        <el-form-item label="数据集目录">
          <el-input v-model="trainForm.dataset_path" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createTask">
          启动训练
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import {
  downloadTrainingResultsApi,
  getTrainingMetricsApi,
  getTrainingStatusApi,
  getTrainingTasksApi,
  startTrainingApi,
  stopTrainingApi,
} from '@/api/training'

echarts.use([TitleComponent, TooltipComponent, LegendComponent, GridComponent, LineChart, CanvasRenderer])

const taskList = ref([])
const loadingTasks = ref(false)
const selectedTask = ref(null)
const latestMetric = ref(null)
const showCreateDialog = ref(false)
const creating = ref(false)

const lossChartRef = ref(null)
const metricChartRef = ref(null)
let lossChart = null
let metricChart = null
let pollTimer = null

const trainForm = ref({
  scene_id: 1,
  model_name: 'yolov11n',
  epochs: 5,
  batch_size: 4,
  img_size: 640,
  device: 'cpu',
  optimizer: 'SGD',
  lr0: 0.01,
  dataset_path: 'datasets/vision_pay',
})

const metricCards = computed(() => {
  const task = selectedTask.value
  const metric = latestMetric.value
  if (!task) return []
  return [
    { label: 'Epoch', value: `${task.current_epoch || 0}/${task.epochs || 0}` },
    { label: '进度', value: `${task.progress || 0}%` },
    { label: 'Box Loss', value: formatNumber(metric?.box_loss) },
    { label: 'Cls Loss', value: formatNumber(metric?.cls_loss) },
    { label: 'mAP@50', value: formatPercent(metric?.map50) },
    { label: 'mAP@50-95', value: formatPercent(metric?.map50_95) },
  ]
})

function statusType(status) {
  return {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }[status] || 'info'
}

function progressStatus(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

function statusText(status) {
  return {
    pending: '等待中',
    running: '训练中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] || status || '-'
}

function formatNumber(value) {
  return value == null ? '-' : Number(value).toFixed(4)
}

function formatPercent(value) {
  return value == null ? '-' : `${(Number(value) * 100).toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

async function fetchTasks() {
  loadingTasks.value = true
  try {
    const res = await getTrainingTasksApi()
    taskList.value = res.items || []
  } finally {
    loadingTasks.value = false
  }
}

async function selectTask(task) {
  selectedTask.value = { ...task }
  latestMetric.value = null
  await nextTick()
  initCharts()
  await refreshSelectedTask()
  startPolling()
}

async function refreshSelectedTask() {
  if (!selectedTask.value) return
  const taskId = selectedTask.value.id
  const [statusRes, metricsRes] = await Promise.all([
    getTrainingStatusApi(taskId),
    getTrainingMetricsApi(taskId),
  ])

  selectedTask.value = { ...selectedTask.value, ...(statusRes.task || {}) }
  latestMetric.value = statusRes.latest_metric || null
  updateCharts(metricsRes.metrics || [])
}

function initCharts() {
  if (lossChart) lossChart.dispose()
  if (metricChart) metricChart.dispose()
  if (lossChartRef.value) lossChart = echarts.init(lossChartRef.value)
  if (metricChartRef.value) metricChart = echarts.init(metricChartRef.value)
  updateCharts([])
}

function updateCharts(metrics) {
  const epochs = metrics.map((item) => item.epoch)
  if (lossChart) {
    lossChart.setOption({
      title: { text: '训练损失曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 56, right: 24, top: 52, bottom: 52 },
      xAxis: { type: 'category', name: 'Epoch', data: epochs },
      yAxis: { type: 'value', name: 'Loss' },
      series: [
        { name: 'Box Loss', type: 'line', smooth: true, data: metrics.map((m) => m.box_loss) },
        { name: 'Cls Loss', type: 'line', smooth: true, data: metrics.map((m) => m.cls_loss) },
        { name: 'DFL Loss', type: 'line', smooth: true, data: metrics.map((m) => m.dfl_loss) },
      ],
    })
  }

  if (metricChart) {
    metricChart.setOption({
      title: { text: '评估指标曲线', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 56, right: 24, top: 52, bottom: 52 },
      xAxis: { type: 'category', name: 'Epoch', data: epochs },
      yAxis: { type: 'value', name: 'Score', min: 0, max: 1 },
      series: [
        { name: 'mAP@50', type: 'line', smooth: true, data: metrics.map((m) => m.map50) },
        { name: 'mAP@50-95', type: 'line', smooth: true, data: metrics.map((m) => m.map50_95) },
        { name: 'Precision', type: 'line', smooth: true, data: metrics.map((m) => m.precision) },
        { name: 'Recall', type: 'line', smooth: true, data: metrics.map((m) => m.recall) },
      ],
    })
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      await refreshSelectedTask()
      if (!['pending', 'running'].includes(selectedTask.value?.status)) {
        stopPolling()
        await fetchTasks()
      }
    } catch {
      stopPolling()
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function createTask() {
  creating.value = true
  try {
    const payload = { ...trainForm.value }
    if (!payload.dataset_path) delete payload.dataset_path
    const task = await startTrainingApi(payload)
    ElMessage.success(`训练任务已创建：${task.task_uuid}`)
    showCreateDialog.value = false
    await fetchTasks()
    const created = taskList.value.find((item) => item.id === task.id)
    await selectTask(created || task)
  } finally {
    creating.value = false
  }
}

async function stopTask(taskId) {
  await ElMessageBox.confirm('确定要停止当前训练任务吗？', '确认停止', { type: 'warning' })
  await stopTrainingApi(taskId)
  ElMessage.success('训练任务已停止')
  await fetchTasks()
  if (selectedTask.value?.id === taskId) {
    await refreshSelectedTask()
  }
}

async function downloadResults(taskUuid) {
  const blob = await downloadTrainingResultsApi(taskUuid)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `training_results_${taskUuid}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function resizeCharts() {
  lossChart?.resize()
  metricChart?.resize()
}

onMounted(() => {
  fetchTasks()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  stopPolling()
  window.removeEventListener('resize', resizeCharts)
  lossChart?.dispose()
  metricChart?.dispose()
})
</script>

<style scoped lang="scss">
.training-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;

  h2 {
    margin: 0;
    font-size: 22px;
    color: $text-primary;
  }

  p {
    margin: 6px 0 0;
    color: $text-secondary;
  }
}

.panel {
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-md;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  font-weight: 600;
  color: $text-primary;
}

.monitor-header {
  align-items: flex-start;

  > div:first-child {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.monitor-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  font-size: 13px;
  font-weight: 400;
  color: $text-secondary;
}

.task-table {
  width: 100%;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(112px, 1fr));
  gap: 12px;
}

.metric-card {
  min-height: 72px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-sm;
  background: #fafafa;

  span {
    display: block;
    color: $text-secondary;
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 8px;
    font-size: 20px;
    color: $text-primary;
  }
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.chart {
  min-height: 340px;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-sm;
}

.empty-monitor {
  padding: 32px 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-md;
}

@media (max-width: 1100px) {
  .metric-grid,
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
