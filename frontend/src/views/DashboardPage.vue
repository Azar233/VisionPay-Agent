<template>
  <div class="dashboard-page" v-loading="loading">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Retail Intelligence</span>
        <h1 class="vp-page-title">数据看板</h1>
        <p class="vp-page-subtitle">汇总当前账号的商品识别任务、处理规模与模型推理表现。</p>
      </div>
      <el-radio-group v-model="periodDays" @change="loadDashboard">
        <el-radio-button :value="7">7 天</el-radio-button>
        <el-radio-button :value="30">30 天</el-radio-button>
        <el-radio-button :value="90">90 天</el-radio-button>
      </el-radio-group>
    </header>

    <section class="metric-grid" aria-label="识别业务指标">
      <article v-for="card in metricCards" :key="card.key" class="metric-card">
        <div :class="['metric-icon', card.tone]"><el-icon><component :is="card.icon" /></el-icon></div>
        <div class="metric-copy">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}<small v-if="card.unit">{{ card.unit }}</small></strong>
        </div>
        <span
          :class="[
            'vp-pill',
            growthTone(card.key, card.inverse) === 'positive' ? 'vp-pill--success' :
            growthTone(card.key, card.inverse) === 'negative' ? 'vp-pill--danger' : ''
          ]"
        >
          {{ growthText(card.key) }}
        </span>
      </article>
    </section>

    <section class="chart-grid">
      <article class="chart-card chart-wide">
        <header><div><span>识别趋势</span><small>任务、图片与商品实例</small></div></header>
        <div ref="trendChartRef" class="chart"></div>
      </article>
      <article class="chart-card">
        <header><div><span>商品类别</span><small>按识别实例统计 Top 8</small></div></header>
        <div ref="classChartRef" class="chart"></div>
      </article>
      <article class="chart-card">
        <header><div><span>业务场景</span><small>按识别任务统计</small></div></header>
        <div ref="sceneChartRef" class="chart"></div>
      </article>
      <article class="chart-card">
        <header><div><span>识别方式</span><small>单图、批量、ZIP 与视频</small></div></header>
        <div ref="typeChartRef" class="chart"></div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getInstanceByDom, init, use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Aim, Camera, PictureFilled, Timer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getClassDistribution,
  getSceneDistribution,
  getStatistics,
  getTrend,
  getTypeDistribution,
} from '@/api/dashboard'
import { useTheme } from '@/composables/useTheme'

const periodDays = ref(30)
const loading = ref(false)
const stats = ref({ total_tasks: 0, total_images: 0, total_objects: 0, avg_inference_time: 0, growth: {} })
const trend = ref([])
const classDistribution = ref([])
const sceneDistribution = ref([])
const typeDistribution = ref([])
const trendChartRef = ref()
const classChartRef = ref()
const sceneChartRef = ref()
const typeChartRef = ref()
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

function formatNumber(value) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0))
}

function growthValue(key) {
  return Number(stats.value.growth?.[key] || 0)
}

function growthText(key) {
  const value = growthValue(key)
  if (value === 0) return '与上期持平'
  return `${value > 0 ? '↑' : '↓'} ${Math.abs(value).toFixed(1)}% 较上期`
}

function growthTone(key, inverse = false) {
  const value = growthValue(key)
  if (!value) return 'neutral'
  const positive = inverse ? value < 0 : value > 0
  return positive ? 'positive' : 'negative'
}

function palette() {
  const style = getComputedStyle(document.documentElement)
  return {
    text: style.getPropertyValue('--vp-text').trim() || '#111827',
    muted: style.getPropertyValue('--vp-muted').trim() || '#6b7280',
    border: style.getPropertyValue('--vp-border').trim() || '#e8eaef',
    surface: style.getPropertyValue('--vp-surface').trim() || '#ffffff',
  }
}

function compactDistribution(items, limit = 8) {
  if (items.length <= limit) return items
  const head = items.slice(0, limit)
  return [...head, { name: '其他', value: items.slice(limit).reduce((sum, item) => sum + item.value, 0) }]
}

function emptyGraphic(message) {
  return [{ type: 'text', left: 'center', top: 'middle', style: { text: message, fill: palette().muted, fontSize: 13 } }]
}

function baseChart(refValue) {
  let chart = getInstanceByDom(refValue)
  if (!chart) {
    chart = init(refValue)
    charts.push(chart)
    resizeObserver?.observe(refValue)
  }
  return chart
}

function renderCharts() {
  if (!trendChartRef.value) return
  const colors = palette()
  const axis = { axisLine: { lineStyle: { color: colors.border } }, axisLabel: { color: colors.muted }, splitLine: { lineStyle: { color: colors.border } } }
  const trendChart = baseChart(trendChartRef.value)
  trendChart.setOption({
    color: ['#2b7fff', '#34d399', '#f59e0b'],
    tooltip: { trigger: 'axis', backgroundColor: colors.surface, borderColor: colors.border, textStyle: { color: colors.text } },
    legend: { top: 0, right: 4, textStyle: { color: colors.muted } },
    grid: { left: 44, right: 18, top: 46, bottom: 30 },
    xAxis: { type: 'category', data: trend.value.map((item) => item.date.slice(5)), boundaryGap: false, ...axis },
    yAxis: { type: 'value', minInterval: 1, ...axis },
    series: [
      { name: '任务', type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: 0.08 }, data: trend.value.map((item) => item.task_count) },
      { name: '图片 / 帧', type: 'line', smooth: true, showSymbol: false, data: trend.value.map((item) => item.image_count) },
      { name: '商品实例', type: 'line', smooth: true, showSymbol: false, data: trend.value.map((item) => item.object_count) },
    ],
  }, true)

  const pieColors = ['#2b7fff', '#34d399', '#f59e0b', '#af52de', '#5ac8fa', '#f87171', '#64d2ff', '#bf5af2', '#9ca3af']
  for (const [element, source, emptyText] of [
    [classChartRef.value, compactDistribution(classDistribution.value), '暂无商品类别数据'],
    [typeChartRef.value, typeDistribution.value, '暂无识别方式数据'],
  ]) {
    const chart = baseChart(element)
    chart.setOption({
      color: pieColors,
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c}（{d}%）', backgroundColor: colors.surface, borderColor: colors.border, textStyle: { color: colors.text } },
      legend: { type: 'scroll', bottom: 0, left: 'center', textStyle: { color: colors.muted }, pageTextStyle: { color: colors.muted } },
      graphic: source.length ? [] : emptyGraphic(emptyText),
      series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '43%'], minAngle: 3, label: { show: false }, data: source }],
    }, true)
  }

  const sceneChart = baseChart(sceneChartRef.value)
  sceneChart.setOption({
    color: ['#2b7fff'],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: colors.surface, borderColor: colors.border, textStyle: { color: colors.text } },
    grid: { left: 24, right: 24, top: 18, bottom: 52, containLabel: true },
    xAxis: { type: 'category', data: sceneDistribution.value.map((item) => item.name), axisLabel: { color: colors.muted, interval: 0, rotate: sceneDistribution.value.length > 4 ? 25 : 0 }, axisLine: axis.axisLine },
    yAxis: { type: 'value', minInterval: 1, ...axis },
    graphic: sceneDistribution.value.length ? [] : emptyGraphic('暂无业务场景数据'),
    series: [{ type: 'bar', data: sceneDistribution.value.map((item) => item.value), barMaxWidth: 48, itemStyle: { borderRadius: [7, 7, 0, 0] } }],
  }, true)
}

async function loadDashboard() {
  loading.value = true
  try {
    const [statisticsData, trendData, classData, sceneData, typeData] = await Promise.all([
      getStatistics(periodDays.value), getTrend(periodDays.value), getClassDistribution(periodDays.value),
      getSceneDistribution(periodDays.value), getTypeDistribution(periodDays.value),
    ])
    stats.value = statisticsData
    trend.value = trendData.trend || []
    classDistribution.value = classData.distribution || []
    sceneDistribution.value = sceneData.distribution || []
    typeDistribution.value = typeData.distribution || []
    await nextTick()
    renderCharts()
  } catch {
    ElMessage.error('数据看板加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

watch(isDark, () => nextTick(renderCharts))

onMounted(() => {
  resizeObserver = new ResizeObserver(() => charts.forEach((chart) => chart.resize()))
  loadDashboard()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.splice(0).forEach((chart) => chart.dispose())
})
</script>

<style lang="scss" scoped>
.dashboard-page { min-height: 100%; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.metric-card { min-width: 0; padding: 22px; display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 14px; background: $surface-color; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; }
.metric-icon { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; font-size: 20px; }
.metric-icon.blue { color: $primary-color; background: $primary-soft; }
.metric-icon.green { color: $success-color; background: var(--vp-success-bg); }
.metric-icon.orange { color: $warning-color; background: var(--vp-warning-bg); }
.metric-icon.purple { color: $secondary-color; background: color-mix(in srgb, $secondary-color 12%, transparent); }
.metric-copy { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.metric-copy > span { color: $text-secondary; font-size: 12px; }
.metric-copy strong { overflow: hidden; color: $text-primary; font-size: 30px; font-weight: 600; letter-spacing: -.04em; text-overflow: ellipsis; }
.metric-copy small { margin-left: 4px; color: $text-secondary; font-size: 12px; font-weight: 500; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.chart-card { min-width: 0; overflow: hidden; background: $surface-color; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; }
.chart-card.chart-wide { grid-column: 1 / -1; }
.chart-card header { min-height: 56px; padding: 0 22px; display: flex; align-items: center; border-bottom: 1px solid $border-color; }
.chart-card header div { display: flex; flex-direction: column; gap: 4px; }
.chart-card header span { color: $text-primary; font-weight: 600; }
.chart-card header small { color: $text-secondary; }
.chart { width: 100%; height: 330px; }
.chart-wide .chart { height: 360px; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 760px) { .dashboard-page { padding: 16px; }.page-header { align-items: flex-start; flex-direction: column; }.metric-grid, .chart-grid { grid-template-columns: 1fr; }.chart-card.chart-wide { grid-column: auto; }.chart { height: 300px; } }
</style>
