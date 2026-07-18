<template>
  <div class="dashboard-page" v-loading="loading">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Retail Intelligence</span>
        <h1 class="vp-page-title">数据概览</h1>
        <p class="vp-page-subtitle">分别查看商品识别业务与多 Agent 模型调用情况，避免不同类型的数据相互干扰。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="refreshCurrent">刷新当前概览</el-button>
    </header>

    <section class="dashboard-workspace">
      <el-tabs v-model="activeSection" class="dashboard-tabs" @tab-change="handleSectionChange">
        <el-tab-pane name="detection">
          <template #label>
            <span class="tab-label"><el-icon><View /></el-icon><span>识别概览</span><small>{{ formatNumber(stats.total_tasks) }}</small></span>
          </template>
          <div class="dashboard-pane">
            <div class="pane-toolbar">
              <div><strong>识别数据概览</strong><small>识别任务、处理规模与商品分布</small></div>
              <div class="period-switch" role="group" aria-label="识别概览时间范围">
                <button v-for="option in periodOptions" :key="option.value" type="button" :class="{ active: detectionPeriodDays === option.value }" @click="selectDetectionPeriod(option.value)">{{ option.label }}</button>
              </div>
            </div>

            <section class="metric-grid" aria-label="识别业务指标">
              <article v-for="card in metricCards" :key="card.key" class="metric-card">
                <div :class="['metric-icon', card.tone]"><el-icon><component :is="card.icon" /></el-icon></div>
                <div class="metric-copy"><span>{{ card.label }}</span><strong>{{ card.value }}<small v-if="card.unit">{{ card.unit }}</small></strong></div>
                <span :class="['growth', growthTone(card.key, card.inverse)]">{{ growthText(card.key) }}</span>
              </article>
            </section>

            <section class="chart-grid">
              <article class="chart-card chart-wide">
                <header class="card-header">
                  <div><span>识图趋势</span><small>任务、图片与商品实例</small></div>
                </header>
                <div ref="trendChartRef" class="chart chart-trend"></div>
              </article>
              <article class="chart-card">
                <header class="card-header"><div><span>商品类别</span><small>按识别实例统计 Top 8</small></div></header>
                <div ref="classChartRef" class="chart"></div>
              </article>
              <article class="chart-card">
                <header class="card-header"><div><span>识别方式</span><small>单图、批量、ZIP 与视频</small></div></header>
                <div ref="typeChartRef" class="chart"></div>
              </article>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane name="model">
          <template #label>
            <span class="tab-label"><el-icon><Connection /></el-icon><span>模型调用</span><small>{{ formatNumber(modelUsage.summary.total_calls) }}</small></span>
          </template>
          <div class="dashboard-pane">
            <div class="pane-toolbar">
              <div><strong>模型调用概览</strong><small>大模型请求、Token 与 Agent 使用情况</small></div>
              <div class="period-switch" role="group" aria-label="模型调用时间范围">
                <button v-for="option in periodOptions" :key="option.value" type="button" :class="{ active: modelPeriodDays === option.value }" @click="selectModelPeriod(option.value)">{{ option.label }}</button>
              </div>
            </div>

            <section class="metric-grid" aria-label="模型调用指标">
              <article v-for="card in modelMetricCards" :key="card.key" class="metric-card model-metric-card">
                <div :class="['metric-icon', card.tone]"><el-icon><component :is="card.icon" /></el-icon></div>
                <div class="metric-copy"><span>{{ card.label }}</span><strong>{{ card.value }}<small v-if="card.unit">{{ card.unit }}</small></strong></div>
                <span class="metric-note">{{ card.note }}</span>
              </article>
            </section>

            <section class="model-chart-grid">
              <article class="chart-card">
                <header class="card-header"><div><span>调用趋势</span><small>模型请求次数与 Token 消耗</small></div></header>
                <div ref="modelTrendChartRef" class="chart"></div>
              </article>
              <article class="chart-card">
                <header class="card-header"><div><span>Agent 使用分布</span><small>按实际模型调用次数统计</small></div></header>
                <div ref="agentChartRef" class="chart"></div>
              </article>
            </section>

            <article class="chart-card recent-card">
              <header class="card-header"><div><span>最近模型调用</span><small>当前账号最近 8 次 Agent 响应</small></div><span class="record-count">{{ modelUsage.recent.length }} 条记录</span></header>
              <el-table :data="modelUsage.recent" row-key="id" empty-text="当前周期内暂无模型调用记录">
                <el-table-column label="调用时间" min-width="168"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
                <el-table-column label="模型" min-width="150" show-overflow-tooltip><template #default="{ row }"><span class="model-name"><el-icon><Cpu /></el-icon>{{ row.model_name }}</span></template></el-table-column>
                <el-table-column label="Agent" min-width="155"><template #default="{ row }"><span :class="['agent-badge', row.agent]"><i></i>{{ row.agent_label }}</span></template></el-table-column>
                <el-table-column prop="call_count" label="模型请求" width="94" align="right" />
                <el-table-column label="输入 / 输出 Token" min-width="160" align="right"><template #default="{ row }">{{ formatNumber(row.input_tokens) }} / {{ formatNumber(row.output_tokens) }}</template></el-table-column>
                <el-table-column label="总 Token" width="112" align="right"><template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template></el-table-column>
                <el-table-column label="耗时" width="108" align="right"><template #default="{ row }">{{ formatDuration(row.latency_ms) }}</template></el-table-column>
                <el-table-column label="状态" width="92" align="center"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'danger'" effect="light" round>{{ row.status === 'completed' ? '成功' : '失败' }}</el-tag></template></el-table-column>
              </el-table>
            </article>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getInstanceByDom, init, use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Aim, Camera, CircleCheck, Connection, Cpu, DataLine, PictureFilled, Refresh, Timer, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getClassDistribution, getModelUsage, getStatistics, getTrend, getTypeDistribution } from '@/api/dashboard'
import { useTheme } from '@/composables/useTheme'

const activeSection = ref('detection')
const detectionPeriodDays = ref(30)
const modelPeriodDays = ref(30)
const periodOptions = [
  { value: 1, label: '1 天' },
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
]
const detectionLoading = ref(false)
const trendLoading = ref(false)
const modelLoading = ref(false)
const loading = computed(() => detectionLoading.value || trendLoading.value || modelLoading.value)
const stats = ref({ total_tasks: 0, total_images: 0, total_objects: 0, avg_inference_time: 0, growth: {} })
const trend = ref([])
const trendGranularity = ref('day')
const classDistribution = ref([])
const typeDistribution = ref([])
const modelUsage = ref({
  summary: { total_calls: 0, total_turns: 0, total_tokens: 0, avg_latency_ms: 0, success_rate: 0 },
  trend: [], agent_distribution: [], recent: [], granularity: 'day',
})
const trendChartRef = ref()
const classChartRef = ref()
const typeChartRef = ref()
const modelTrendChartRef = ref()
const agentChartRef = ref()
const charts = []
let resizeObserver
const { isDark } = useTheme()

use([LineChart, PieChart, BarChart, TooltipComponent, LegendComponent, GridComponent, GraphicComponent, CanvasRenderer])

const metricCards = computed(() => [
  { key: 'tasks', label: '识别任务', value: formatNumber(stats.value.total_tasks), icon: Camera, tone: 'blue' },
  { key: 'images', label: '处理图片 / 帧', value: formatNumber(stats.value.total_images), icon: PictureFilled, tone: 'green' },
  { key: 'objects', label: '商品实例', value: formatNumber(stats.value.total_objects), icon: Aim, tone: 'orange' },
  { key: 'inference_time', label: '单图平均推理', value: Number(stats.value.avg_inference_time || 0).toFixed(1), unit: 'ms', icon: Timer, tone: 'purple', inverse: true },
])

const modelMetricCards = computed(() => {
  const summary = modelUsage.value.summary
  return [
    { key: 'calls', label: '模型请求', value: formatNumber(summary.total_calls), icon: Connection, tone: 'blue', note: `${formatNumber(summary.total_turns)} 次 Agent 响应` },
    { key: 'tokens', label: 'Token 消耗', value: formatCompact(summary.total_tokens), icon: DataLine, tone: 'orange', note: `统计周期 ${modelPeriodDays.value} 天` },
    { key: 'latency', label: '平均响应耗时', value: formatSeconds(summary.avg_latency_ms), unit: 's', icon: Timer, tone: 'purple', note: '按 Agent 响应统计' },
    { key: 'success', label: '调用成功率', value: Number(summary.success_rate || 0).toFixed(1), unit: '%', icon: CircleCheck, tone: 'green', note: '失败响应单独计入' },
  ]
})

function formatNumber(value) { return new Intl.NumberFormat('zh-CN').format(Number(value || 0)) }
function formatCompact(value) { return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(value || 0)) }
function formatSeconds(value) { return (Number(value || 0) / 1000).toFixed(1) }
function formatDuration(value) { return value == null ? '—' : value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms` }
function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}
function growthValue(key) { return Number(stats.value.growth?.[key] || 0) }
function growthText(key) {
  const value = growthValue(key)
  if (value === 0) return '与上期持平'
  return `${value > 0 ? '↑' : '↓'} ${Math.abs(value).toFixed(1)}% 较上期`
}
function growthTone(key, inverse = false) {
  const value = growthValue(key)
  if (!value) return 'neutral'
  return (inverse ? value < 0 : value > 0) ? 'positive' : 'negative'
}
function palette() {
  const style = getComputedStyle(document.documentElement)
  return {
    text: style.getPropertyValue('--vp-text').trim() || '#1d1d1f',
    muted: style.getPropertyValue('--vp-muted').trim() || '#6e6e73',
    border: style.getPropertyValue('--vp-border').trim() || '#e5e5e7',
    surface: style.getPropertyValue('--vp-surface').trim() || '#fff',
  }
}
function compactDistribution(items, limit = 8) {
  if (items.length <= limit) return items
  return [...items.slice(0, limit), { name: '其他', value: items.slice(limit).reduce((sum, item) => sum + item.value, 0) }]
}
function emptyGraphic(message) { return [{ type: 'text', left: 'center', top: 'middle', style: { text: message, fill: palette().muted, fontSize: 13 } }] }
function baseChart(element) {
  if (!element) return null
  let chart = getInstanceByDom(element)
  if (!chart) { chart = init(element); charts.push(chart); resizeObserver?.observe(element) }
  return chart
}
function trendLabel(item) {
  if (trendGranularity.value === 'hour') return item.date.slice(11, 16)
  return item.date.slice(5)
}
function modelTrendLabel(item) {
  if (modelUsage.value.granularity === 'hour') return item.date.slice(11, 16)
  return item.date.slice(5)
}

function renderActiveCharts() {
  const colors = palette()
  const axis = { axisLine: { lineStyle: { color: colors.border } }, axisLabel: { color: colors.muted }, splitLine: { lineStyle: { color: colors.border } } }
  const tooltip = { backgroundColor: colors.surface, borderColor: colors.border, textStyle: { color: colors.text } }
  const pieColors = ['#0071e3', '#34c759', '#ff9f0a', '#af52de', '#5ac8fa', '#ff375f', '#64d2ff', '#bf5af2', '#8e8e93']
  const renderPies = (items) => items.forEach(([element, source, emptyText]) => {
    const chart = baseChart(element)
    chart?.setOption({
      color: pieColors, tooltip: { trigger: 'item', formatter: '{b}<br/>{c}（{d}%）', ...tooltip },
      legend: {
        type: 'plain', orient: 'vertical', top: 'middle', left: '63%', right: 12,
        itemWidth: 13, itemHeight: 9, itemGap: 12,
        textStyle: { color: colors.muted, fontSize: 12, lineHeight: 17 },
      },
      graphic: source.length ? [] : emptyGraphic(emptyText),
      series: [{ type: 'pie', radius: ['38%', '64%'], center: ['34%', '50%'], minAngle: 3, label: { show: false }, data: source }],
    }, true)
  })

  if (activeSection.value === 'detection') {
    const trendChart = baseChart(trendChartRef.value)
    trendChart?.setOption({
      color: ['#0071e3', '#34c759', '#ff9f0a'], tooltip: { trigger: 'axis', ...tooltip },
      legend: { top: 0, right: 4, textStyle: { color: colors.muted } }, grid: { left: 44, right: 18, top: 46, bottom: 34 },
      xAxis: {
        type: 'category', data: trend.value.map(trendLabel), boundaryGap: false, ...axis,
        axisLabel: { ...axis.axisLabel, interval: trendGranularity.value === 'hour' ? 0 : 'auto' },
      },
      yAxis: { type: 'value', minInterval: 1, ...axis },
      series: [
        { name: '任务', type: 'line', smooth: true, showSymbol: trend.value.length <= 7, symbolSize: 6, areaStyle: { opacity: 0.08 }, data: trend.value.map((item) => item.task_count) },
        { name: '图片 / 帧', type: 'line', smooth: true, showSymbol: trend.value.length <= 7, symbolSize: 6, data: trend.value.map((item) => item.image_count) },
        { name: '商品实例', type: 'line', smooth: true, showSymbol: trend.value.length <= 7, symbolSize: 6, data: trend.value.map((item) => item.object_count) },
      ],
    }, true)
    renderPies([
      [classChartRef.value, compactDistribution(classDistribution.value), '暂无商品类别数据'],
      [typeChartRef.value, typeDistribution.value, '暂无识别方式数据'],
    ])
    return
  }

  renderPies([[agentChartRef.value, modelUsage.value.agent_distribution, '暂无 Agent 调用数据']])
  const modelTrendChart = baseChart(modelTrendChartRef.value)
  modelTrendChart?.setOption({
    color: ['#0071e3', '#af52de'], tooltip: { trigger: 'axis', ...tooltip },
    legend: { top: 0, right: 4, textStyle: { color: colors.muted } }, grid: { left: 48, right: 52, top: 46, bottom: 34 },
    xAxis: {
      type: 'category', data: modelUsage.value.trend.map(modelTrendLabel), ...axis,
      axisLabel: { ...axis.axisLabel, interval: modelUsage.value.granularity === 'hour' ? 0 : 'auto' },
    },
    yAxis: [
      { type: 'value', minInterval: 1, name: '次', nameTextStyle: { color: colors.muted }, ...axis },
      { type: 'value', axisLine: axis.axisLine, axisLabel: { color: colors.muted }, splitLine: { show: false } },
    ],
    series: [
      { name: '模型请求', type: 'bar', barMaxWidth: 24, itemStyle: { borderRadius: [5, 5, 0, 0] }, data: modelUsage.value.trend.map((item) => item.calls) },
      { name: 'Token', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: modelUsage.value.trend.map((item) => item.tokens) },
    ],
  }, true)
}

async function handleSectionChange() {
  await nextTick()
  renderActiveCharts()
  charts.forEach((chart) => chart.resize())
}

function selectDetectionPeriod(value) {
  if (detectionPeriodDays.value === value) return
  detectionPeriodDays.value = value
  Promise.all([loadDetectionOverview(), loadDetectionTrend()])
}

function selectModelPeriod(value) {
  if (modelPeriodDays.value === value) return
  modelPeriodDays.value = value
  loadModelUsage()
}

function refreshCurrent() {
  if (activeSection.value === 'model') return loadModelUsage()
  return Promise.all([loadDetectionOverview(), loadDetectionTrend()])
}

async function loadDetectionOverview() {
  detectionLoading.value = true
  try {
    const [statisticsData, classData, typeData] = await Promise.all([
      getStatistics(detectionPeriodDays.value), getClassDistribution(detectionPeriodDays.value), getTypeDistribution(detectionPeriodDays.value),
    ])
    stats.value = statisticsData
    classDistribution.value = classData.distribution || []
    typeDistribution.value = typeData.distribution || []
    if (activeSection.value === 'detection') { await nextTick(); renderActiveCharts() }
  } catch { ElMessage.error('识别业务概览加载失败，请稍后重试') } finally { detectionLoading.value = false }
}
async function loadDetectionTrend() {
  trendLoading.value = true
  try {
    const data = await getTrend(
      detectionPeriodDays.value === 1
        ? { days: 1, hours: 24, bucketHours: 2 }
        : { days: detectionPeriodDays.value },
    )
    trend.value = data.trend || []
    trendGranularity.value = data.granularity || 'day'
    if (activeSection.value === 'detection') { await nextTick(); renderActiveCharts() }
  } catch { ElMessage.error('识图趋势加载失败，请稍后重试') } finally { trendLoading.value = false }
}
async function loadModelUsage() {
  modelLoading.value = true
  try {
    modelUsage.value = modelPeriodDays.value === 1
      ? await getModelUsage(1, 8, { hours: 24, bucketHours: 2 })
      : await getModelUsage(modelPeriodDays.value, 8)
    if (activeSection.value === 'model') { await nextTick(); renderActiveCharts() }
  } catch { ElMessage.error('模型调用概览加载失败，请稍后重试') } finally { modelLoading.value = false }
}

watch(isDark, () => nextTick(renderActiveCharts))
onMounted(() => {
  resizeObserver = new ResizeObserver(() => charts.forEach((chart) => chart.resize()))
  Promise.all([loadDetectionOverview(), loadDetectionTrend(), loadModelUsage()])
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.splice(0).forEach((chart) => chart.dispose())
})
</script>

<style lang="scss" scoped>
.dashboard-page { min-height: 100%; padding: 32px; display: flex; flex-direction: column; gap: 18px; color: $text-primary; background: $bg-color; }
.page-header { padding: 8px 0 14px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.page-header h1 { margin: 10px 0 0; color: $text-primary; font-family: 'Space Grotesk', 'DM Sans', sans-serif; font-size: 40px; line-height: 1.08; }
.page-header p { max-width: 620px; margin: 12px 0 0; color: $text-secondary; font-size: 16px; line-height: 1.6; }
.dashboard-workspace { min-width: 0; }.dashboard-tabs :deep(.el-tabs__header) { margin: 0 0 16px; padding: 5px; border: 1px solid $border-color; border-radius: 14px; background: $surface-muted; }.dashboard-tabs :deep(.el-tabs__nav-wrap::after),.dashboard-tabs :deep(.el-tabs__active-bar) { display: none; }.dashboard-tabs :deep(.el-tabs__item) { height: 42px; padding: 0 7px; color: $text-secondary; }.dashboard-tabs :deep(.el-tabs__item.is-active) { color: $text-primary; }.tab-label { height: 34px; padding: 0 13px; display: inline-flex; align-items: center; gap: 7px; border-radius: 10px; transition: .2s ease; }.dashboard-tabs :deep(.is-active) .tab-label { color: $primary-color; background: $surface-color; box-shadow: 0 5px 14px rgba(15,23,42,.07); }.tab-label small { min-width: 20px; padding: 2px 6px; border-radius: 999px; color: $text-placeholder; background: color-mix(in srgb,$border-color 60%,transparent); font-size: 9px; text-align: center; }.dashboard-tabs :deep(.is-active) .tab-label small { color: $primary-color; background: $primary-soft; }
.dashboard-pane { display: flex; flex-direction: column; gap: 16px; }.pane-toolbar { min-height: 54px; padding: 2px 2px 8px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }.pane-toolbar > div:first-child { display: flex; flex-direction: column; gap: 4px; }.pane-toolbar strong { font-size: 17px; }.pane-toolbar small { color: $text-secondary; font-size: 12px; }
.period-switch { max-width: 100%; padding: 3px; display: inline-flex !important; flex: none; flex-direction: row !important; align-items: center; gap: 2px !important; overflow-x: auto; border: 1px solid $border-color; border-radius: 12px; background: $surface-muted; white-space: nowrap; scrollbar-width: none; }.period-switch::-webkit-scrollbar { display: none; }.period-switch button { height: 30px; padding: 0 12px; flex: none; border: 0; border-radius: 9px; color: $text-secondary; background: transparent; font: inherit; font-size: 12px; cursor: pointer; transition: color .18s ease, background .18s ease, box-shadow .18s ease; }.period-switch button:hover { color: $text-primary; }.period-switch button.active { color: $primary-color; background: $surface-color; box-shadow: 0 3px 10px rgba(15,23,42,.08); font-weight: 650; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.metric-card { min-width: 0; padding: 22px; display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 14px; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }
.metric-icon { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; font-size: 20px; }.metric-icon.blue { color: #0071e3; background: rgba(0,113,227,.1); }.metric-icon.green { color: #248a3d; background: rgba(52,199,89,.12); }.metric-icon.orange { color: #c93400; background: rgba(255,159,10,.13); }.metric-icon.purple { color: #8944ab; background: rgba(175,82,222,.12); }
.metric-copy { min-width: 0; display: flex; flex-direction: column; gap: 5px; }.metric-copy > span { color: $text-secondary; font-size: 12px; }.metric-copy strong { overflow: hidden; color: $text-primary; font-size: 30px; font-weight: 600; letter-spacing: -.04em; text-overflow: ellipsis; }.metric-copy small { margin-left: 4px; color: $text-secondary; font-size: 12px; font-weight: 500; }
.growth,.metric-note { grid-column: 1 / -1; width: fit-content; font-size: 11px; }.growth { padding: 5px 8px; border-radius: 999px; font-weight: 600; }.growth.positive { color: $success-color; background: color-mix(in srgb, $success-color 12%, transparent); }.growth.negative { color: $danger-color; background: color-mix(in srgb, $danger-color 10%, transparent); }.growth.neutral { color: $text-secondary; background: $surface-muted; }.metric-note { color: $text-secondary; }.model-metric-card { min-height: 132px; }
.chart-grid,.model-chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }.chart-card { min-width: 0; overflow: hidden; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }.chart-card.chart-wide { grid-column: 1 / -1; }.model-chart-grid { grid-template-columns: minmax(0, 1.45fr) minmax(340px, .55fr); }
.card-header { min-height: 70px; padding: 0 22px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid $border-color; }.card-header > div:not(.period-switch) { display: flex; flex-direction: column; gap: 4px; }.card-header span { color: $text-primary; font-weight: 600; }.card-header small { color: $text-secondary; }.chart { width: 100%; height: 330px; }.chart-trend { height: 360px; }
.recent-card { overflow: visible; }.recent-card :deep(.el-table) { border-radius: 0 0 $border-radius-md $border-radius-md; }.record-count { color: $text-secondary !important; font-size: 12px; font-weight: 500 !important; }.model-name,.agent-badge { display: inline-flex; align-items: center; gap: 7px; }.model-name { color: $text-primary; font-weight: 600; }.agent-badge { font-weight: 700; }.agent-badge i { width: 8px; height: 8px; border-radius: 50%; background: #0071e3; }.agent-badge.dataset i { background: #8b5cf6; }.agent-badge.training i { background: #0ea5e9; }.agent-badge.catalog i { background: #f59e0b; }.agent-badge.knowledge i { background: #10b981; }
:global(html.dark .dashboard-tabs .el-tabs__header) { background: rgba(22,22,24,.9); border-color: rgba(255,255,255,.1); }:global(html.dark .period-switch) { background: rgba(22,22,24,.9); border-color: rgba(255,255,255,.1); }:global(html.dark .period-switch button.active) { background: #2c2c2e; box-shadow: 0 4px 12px rgba(0,0,0,.24); }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, 1fr); }.model-chart-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .dashboard-page { padding: 20px; }.page-header { align-items: flex-start; flex-direction: column; }.page-header h1 { font-size: 30px; }.metric-grid,.chart-grid { grid-template-columns: 1fr; }.chart-card.chart-wide { grid-column: auto; }.card-header { padding: 14px 18px; align-items: flex-start; flex-wrap: wrap; }.period-switch { width: fit-content; }.pane-toolbar { align-items: flex-start; flex-direction: column; }.chart { height: 300px; } }
@media (max-width: 520px) { .dashboard-tabs :deep(.el-tabs__item) { padding: 0 2px; }.tab-label { padding: 0 9px; }.tab-label small { display: none; }.period-switch button { padding: 0 10px; } }
</style>
