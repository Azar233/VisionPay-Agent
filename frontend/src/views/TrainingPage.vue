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
        <el-table-column prop="device" label="设备" width="170" />
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
        <el-table-column label="操作" width="420" fixed="right">
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
            <el-button size="small" text @click="openLogDrawer(row)">
              Log
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openEvalDrawer(row)"
            >
              评估
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openExportDialog(row)"
            >
              导出
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="downloadWeights(row)"
            >
              权重
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              size="small"
              text
              @click="openPredictDialog(row)"
            >
              测试
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
          <el-slider v-model="trainForm.epochs" :min="1" :max="300" :step="1" show-input />
        </el-form-item>

        <el-form-item label="批次大小">
          <el-input-number v-model="trainForm.batch_size" :min="1" :max="512" />
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
          <div class="device-field">
            <el-select
              v-model="trainForm.device"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入设备，如 0,1,2,3,4,5,6,7"
            >
              <el-option
                v-for="option in deviceOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <p class="form-tip">多卡训练使用 Ultralytics DDP；batch_size 是总 batch，会分摊到每张 GPU。</p>
          </div>
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

        <el-form-item label="场景增强">
          <el-switch v-model="trainForm.checkout_augment" />
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

    <el-drawer
      v-model="showLogDrawer"
      size="70%"
      :title="logDrawerTitle"
      direction="rtl"
      @closed="stopLogPolling"
    >
      <div class="log-toolbar">
        <div class="log-meta">
          <span>Task {{ logTask?.task_uuid || '-' }}</span>
          <span v-if="logPath">{{ logPath }}</span>
        </div>
        <div class="log-actions">
          <el-switch v-model="autoRefreshLog" active-text="Auto refresh" />
          <el-button size="small" :loading="loadingLog" @click="refreshLog">
            Refresh
          </el-button>
        </div>
      </div>

      <el-empty v-if="!logExists && !loadingLog" description="Log file has not been generated" />
      <pre v-else ref="logContentRef" class="log-content">{{ logText }}</pre>
    </el-drawer>

    <el-drawer
      v-model="showEvalDrawer"
      size="70%"
      title="模型评估报告"
      direction="rtl"
    >
      <div class="eval-toolbar">
        <div class="log-meta">
          <span>Task {{ evalTask?.task_uuid || '-' }}</span>
          <span v-if="evalReport?.report_path">{{ evalReport.report_path }}</span>
        </div>
        <div class="eval-actions">
          <el-select v-model="evalForm.split" size="small">
            <el-option label="val" value="val" />
            <el-option label="test" value="test" />
            <el-option label="train" value="train" />
          </el-select>
          <el-input-number
            v-model="evalForm.conf"
            size="small"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="3"
          />
          <el-input-number
            v-model="evalForm.iou"
            size="small"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="2"
          />
          <el-button size="small" type="primary" :loading="evaluating" @click="runEvaluation">
            运行评估
          </el-button>
        </div>
      </div>

      <el-skeleton v-if="evaluating && !evalReport" :rows="6" animated />
      <template v-else-if="evalReport">
        <div class="metric-grid">
          <div v-for="item in evalMetricCards" :key="item.label" class="metric-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <div class="eval-columns">
          <section class="eval-section">
            <h3>弱势类别 Top 10</h3>
            <el-table :data="weakClassRows" size="small" height="280" empty-text="暂无每类 AP">
              <el-table-column prop="class_name" label="类别" min-width="160" />
              <el-table-column label="AP" width="100">
                <template #default="{ row }">{{ formatPercent(row.ap) }}</template>
              </el-table-column>
            </el-table>
          </section>

          <section class="eval-section">
            <h3>评估产物</h3>
            <ul v-if="artifactRows.length" class="artifact-list">
              <li v-for="item in artifactRows" :key="item.name">
                <strong>{{ item.name }}</strong>
                <span>{{ item.path }}</span>
              </li>
            </ul>
            <el-empty v-else description="暂无混淆矩阵或曲线图" />
          </section>
        </div>
      </template>
      <el-empty v-else description="点击运行评估生成报告" />
    </el-drawer>

    <el-dialog
      v-model="showExportDialog"
      title="导出模型版本"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form :model="exportForm" label-width="100px">
        <el-form-item label="任务">
          <el-input :model-value="exportTask?.task_uuid || '-'" disabled />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input v-model="exportForm.version" placeholder="v1.0.0" />
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="exportForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-switch v-model="exportForm.set_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exporting" @click="submitExport">
          导出
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showPredictDialog"
      title="测试图验证"
      width="860px"
      :close-on-click-modal="false"
      @closed="clearPredictState"
    >
      <div class="predict-layout">
        <section class="predict-panel">
          <div class="predict-controls">
            <input class="file-input" type="file" accept="image/*" @change="onPredictFileChange" />
            <el-form label-width="80px" class="predict-form">
              <el-form-item label="置信度">
                <el-input-number
                  v-model="predictForm.conf"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                />
              </el-form-item>
              <el-form-item label="IoU">
                <el-input-number
                  v-model="predictForm.iou"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                />
              </el-form-item>
              <el-form-item label="设备">
                <el-input v-model="predictForm.device" />
              </el-form-item>
            </el-form>
            <el-button
              type="primary"
              :loading="predicting"
              :disabled="!predictFile"
              @click="runPredict"
            >
              开始检测
            </el-button>
          </div>
          <img v-if="predictPreview" class="preview-image" :src="predictPreview" alt="preview" />
        </section>

        <section class="predict-panel">
          <template v-if="predictResult">
            <div class="predict-summary">
              <span>目标数：{{ predictResult.total_objects }}</span>
              <span>耗时：{{ formatMs(predictResult.inference_time) }}</span>
            </div>
            <img
              v-if="predictResult.annotated_image"
              class="result-image"
              :src="predictResult.annotated_image"
              alt="prediction"
            />
            <el-table :data="predictResult.detections || []" size="small" height="220">
              <el-table-column prop="class_name" label="类别" min-width="130" />
              <el-table-column label="置信度" width="100">
                <template #default="{ row }">{{ formatPercent(row.confidence) }}</template>
              </el-table-column>
              <el-table-column label="BBox" min-width="180">
                <template #default="{ row }">{{ formatBox(row.bbox) }}</template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty v-else description="上传图片后运行检测" />
        </section>
      </div>
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
  downloadTrainingModelApi,
  downloadTrainingResultsApi,
  exportTrainingModelApi,
  getTrainingLogApi,
  getTrainingMetricsApi,
  getTrainingStatusApi,
  getTrainingTasksApi,
  predictTrainingImageApi,
  startTrainingApi,
  stopTrainingApi,
  validateTrainingTaskApi,
} from '@/api/training'

echarts.use([TitleComponent, TooltipComponent, LegendComponent, GridComponent, LineChart, CanvasRenderer])

const taskList = ref([])
const loadingTasks = ref(false)
const selectedTask = ref(null)
const latestMetric = ref(null)
const showCreateDialog = ref(false)
const creating = ref(false)

const showLogDrawer = ref(false)
const logTask = ref(null)
const logLines = ref([])
const logPath = ref('')
const logExists = ref(false)
const loadingLog = ref(false)
const autoRefreshLog = ref(true)
const logContentRef = ref(null)

const showEvalDrawer = ref(false)
const evalTask = ref(null)
const evalReport = ref(null)
const evaluating = ref(false)
const evalForm = ref({
  split: 'val',
  conf: 0.001,
  iou: 0.6,
  device: '0',
})

const showExportDialog = ref(false)
const exportTask = ref(null)
const exportForm = ref({
  version: '',
  description: '',
  set_default: true,
})
const exporting = ref(false)

const showPredictDialog = ref(false)
const predictTask = ref(null)
const predictFile = ref(null)
const predictPreview = ref('')
const predictResult = ref(null)
const predicting = ref(false)
const predictForm = ref({
  conf: 0.25,
  iou: 0.45,
  device: 'cpu',
})
const lossChartRef = ref(null)
const metricChartRef = ref(null)
let lossChart = null
let metricChart = null
let pollTimer = null
let logPollTimer = null

const deviceOptions = [
  { label: 'CPU', value: 'cpu' },
  ...Array.from({ length: 8 }, (_, index) => ({
    label: `GPU ${index}`,
    value: String(index),
  })),
  { label: '2 卡 GPU 0-1', value: '0,1' },
  { label: '4 卡 GPU 0-3', value: '0,1,2,3' },
  { label: '8 卡 GPU 0-7', value: '0,1,2,3,4,5,6,7' },
]

const trainForm = ref({
  scene_id: 1,
  model_name: 'yolov11n',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  device: '0',
  optimizer: 'SGD',
  lr0: 0.01,
  checkout_augment: true,
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

const logText = computed(() => logLines.value.join('\n'))
const logDrawerTitle = computed(() => `Training Log - ${logTask.value?.task_uuid || '-'}`)

const evalMetricCards = computed(() => {
  const report = evalReport.value
  if (!report) return []
  return [
    { label: 'Precision', value: formatPercent(report.precision ?? report.overall?.precision) },
    { label: 'Recall', value: formatPercent(report.recall ?? report.overall?.recall) },
    { label: 'mAP@50', value: formatPercent(report.map50 ?? report.overall?.map50) },
    { label: 'mAP@50-95', value: formatPercent(report.map50_95 ?? report.overall?.map50_95) },
    { label: 'Split', value: report.split || '-' },
    { label: 'Classes', value: Object.keys(report.per_class_ap || {}).length },
  ]
})

const weakClassRows = computed(() => {
  if (Array.isArray(evalReport.value?.weak_classes) && evalReport.value.weak_classes.length) {
    return evalReport.value.weak_classes
  }
  return Object.entries(evalReport.value?.per_class_ap || {})
    .map(([class_name, ap]) => ({ class_name, ap }))
    .filter((item) => item.ap != null)
    .sort((a, b) => Number(a.ap) - Number(b.ap))
    .slice(0, 10)
})

const artifactRows = computed(() =>
  Object.entries(evalReport.value?.artifacts || {}).map(([name, path]) => ({ name, path }))
)

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

function formatMs(value) {
  return value == null ? '-' : `${(Number(value) * 1000).toFixed(1)} ms`
}

function formatBox(value) {
  return Array.isArray(value) ? value.map((item) => Number(item).toFixed(1)).join(', ') : '-'
}

function singleDevice(device) {
  if (!device || device === 'cpu') return device || 'cpu'
  return String(device).split(',')[0]
}

function defaultVersion() {
  const date = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `v${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(
    date.getHours()
  )}${pad(date.getMinutes())}${pad(date.getSeconds())}`
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
    const checkoutAugment = payload.checkout_augment
    delete payload.checkout_augment
    if (checkoutAugment) {
      payload.augment_config = {
        degrees: 180,
        translate: 0.2,
        scale: 0.6,
        flipud: 0.5,
        fliplr: 0.5,
        mosaic: 1.0,
        mixup: 0.1,
        close_mosaic: 10,
      }
    }
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

async function downloadWeights(task) {
  const blob = await downloadTrainingModelApi(task.id)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${task.model_name}_${task.task_uuid}_best.pt`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

async function openEvalDrawer(task) {
  evalTask.value = { ...task }
  evalReport.value = null
  evalForm.value.device = singleDevice(task.device)
  showEvalDrawer.value = true
  await runEvaluation()
}

async function runEvaluation() {
  if (!evalTask.value) return
  evaluating.value = true
  try {
    evalReport.value = await validateTrainingTaskApi(evalTask.value.id, { ...evalForm.value })
    ElMessage.success('评估报告已生成')
  } finally {
    evaluating.value = false
  }
}

function openExportDialog(task) {
  exportTask.value = { ...task }
  exportForm.value = {
    version: defaultVersion(),
    description: '',
    set_default: true,
  }
  showExportDialog.value = true
}

async function submitExport() {
  if (!exportTask.value) return
  exporting.value = true
  try {
    await exportTrainingModelApi(exportTask.value.id, { ...exportForm.value })
    ElMessage.success('模型版本已导出')
    showExportDialog.value = false
  } finally {
    exporting.value = false
  }
}

function openPredictDialog(task) {
  predictTask.value = { ...task }
  predictForm.value.device = singleDevice(task.device)
  predictResult.value = null
  showPredictDialog.value = true
}

function onPredictFileChange(event) {
  const file = event.target.files?.[0]
  if (predictPreview.value) {
    window.URL.revokeObjectURL(predictPreview.value)
  }
  predictFile.value = file || null
  predictResult.value = null
  predictPreview.value = file ? window.URL.createObjectURL(file) : ''
}

async function runPredict() {
  if (!predictTask.value || !predictFile.value) return
  const formData = new FormData()
  formData.append('task_id', predictTask.value.id)
  formData.append('conf', predictForm.value.conf)
  formData.append('iou', predictForm.value.iou)
  formData.append('device', predictForm.value.device || 'cpu')
  formData.append('file', predictFile.value)

  predicting.value = true
  try {
    predictResult.value = await predictTrainingImageApi(formData)
    ElMessage.success(`检测完成：${predictResult.value.total_objects} 个目标`)
  } finally {
    predicting.value = false
  }
}

function clearPredictState() {
  if (predictPreview.value) {
    window.URL.revokeObjectURL(predictPreview.value)
  }
  predictFile.value = null
  predictPreview.value = ''
  predictResult.value = null
}

async function openLogDrawer(task) {
  logTask.value = { ...task }
  logLines.value = []
  logPath.value = task.log_path || ''
  logExists.value = false
  showLogDrawer.value = true
  await refreshLog()
  startLogPolling()
}

async function refreshLog() {
  if (!logTask.value) return
  loadingLog.value = true
  try {
    const res = await getTrainingLogApi(logTask.value.id, 500)
    logExists.value = Boolean(res.exists)
    logPath.value = res.path || logTask.value.log_path || ''
    logLines.value = res.lines || []
    await nextTick()
    if (logContentRef.value) {
      logContentRef.value.scrollTop = logContentRef.value.scrollHeight
    }
  } finally {
    loadingLog.value = false
  }
}

function startLogPolling() {
  stopLogPolling()
  logPollTimer = window.setInterval(async () => {
    if (!showLogDrawer.value || !autoRefreshLog.value) return
    try {
      await refreshLog()
    } catch {
      stopLogPolling()
    }
  }, 3000)
}

function stopLogPolling() {
  if (logPollTimer) {
    window.clearInterval(logPollTimer)
    logPollTimer = null
  }
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
  stopLogPolling()
  clearPredictState()
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

.device-field {
  width: 100%;

  .el-select {
    width: 100%;
  }
}

.form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: $text-secondary;
}

.log-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.log-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: $text-secondary;
  font-size: 13px;

  span {
    overflow-wrap: anywhere;
  }
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.log-content {
  height: calc(100vh - 190px);
  margin: 0;
  padding: 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #d7e1ef;
  background: #111827;
  border-radius: $border-radius-sm;
  font: 12px/1.6 Consolas, 'Courier New', monospace;
}

.eval-toolbar,
.eval-actions,
.predict-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}

.eval-toolbar {
  justify-content: space-between;
  margin-bottom: 16px;
}

.eval-actions {
  flex-wrap: wrap;
  justify-content: flex-end;

  .el-select {
    width: 90px;
  }
}

.eval-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.eval-section,
.predict-panel {
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-sm;
  background: #fff;

  h3 {
    margin: 0 0 12px;
    font-size: 15px;
    color: $text-primary;
  }
}

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  strong {
    color: $text-primary;
  }

  span {
    color: $text-secondary;
    overflow-wrap: anywhere;
  }
}

.predict-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.predict-controls,
.predict-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-input {
  width: 100%;
}

.preview-image,
.result-image {
  display: block;
  width: 100%;
  max-height: 360px;
  margin-top: 12px;
  object-fit: contain;
  border: 1px solid #ebeef5;
  border-radius: $border-radius-sm;
  background: #f5f7fa;
}

.predict-summary {
  justify-content: space-between;
  margin-bottom: 12px;
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
  .chart-grid,
  .eval-columns,
  .predict-layout {
    grid-template-columns: 1fr;
  }
}
</style>
