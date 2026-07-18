<template>
  <div class="history-page">
    <header class="page-header">
      <div>
        <span class="vp-kicker">Activity &amp; Audit</span>
        <h1 class="vp-page-title">历史记录</h1>
        <p class="vp-page-subtitle">集中追溯商品识别、Agent 调用和模型生命周期，快速还原系统在什么时间执行了什么操作。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="refreshing" @click="refreshCurrent">刷新当前记录</el-button>
      </div>
    </header>

    <section class="summary-grid">
      <article class="detection"><span><el-icon><View /></el-icon></span><div><small>识别任务</small><strong>{{ overview.detection_tasks }}</strong><p>当前账号累计检测</p></div></article>
      <article class="agent"><span><el-icon><Connection /></el-icon></span><div><small>Agent 调用</small><strong>{{ overview.agent_calls }}</strong><p>今日 {{ overview.today_agent_calls }} 次</p></div></article>
      <article class="model"><span><el-icon><Cpu /></el-icon></span><div><small>模型版本</small><strong>{{ overview.models }}</strong><p>{{ overview.active_models }} 个处于活动状态</p></div></article>
      <article class="coverage"><span><el-icon><Clock /></el-icon></span><div><small>记录范围</small><strong>3</strong><p>检测、Agent 与模型</p></div></article>
    </section>

    <section class="history-workspace card-container">
      <el-tabs v-model="activeTab" class="history-tabs" @tab-change="handleTabChange">
        <el-tab-pane name="detection">
          <template #label><span class="tab-label"><el-icon><View /></el-icon><span>识别记录</span><small>{{ overview.detection_tasks }}</small></span></template>
          <DetectionHistoryPanel ref="detectionPanel" @changed="loadOverview" />
        </el-tab-pane>
        <el-tab-pane name="agent">
          <template #label><span class="tab-label"><el-icon><Connection /></el-icon><span>Agent 调用</span><small>{{ overview.agent_calls }}</small></span></template>
          <AgentHistoryPanel v-if="loadedTabs.agent" ref="agentPanel" />
        </el-tab-pane>
        <el-tab-pane name="model">
          <template #label><span class="tab-label"><el-icon><Cpu /></el-icon><span>模型历史</span><small>{{ overview.models }}</small></span></template>
          <ModelHistoryPanel v-if="loadedTabs.model" ref="modelPanel" />
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { Clock, Connection, Cpu, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentHistoryPanel from '@/components/history/AgentHistoryPanel.vue'
import DetectionHistoryPanel from '@/components/history/DetectionHistoryPanel.vue'
import ModelHistoryPanel from '@/components/history/ModelHistoryPanel.vue'
import { getHistoryOverview } from '@/api/history'

const activeTab = ref('detection')
const refreshing = ref(false)
const detectionPanel = ref(null)
const agentPanel = ref(null)
const modelPanel = ref(null)
const loadedTabs = reactive({ detection: true, agent: false, model: false })
const overview = reactive({ detection_tasks: 0, agent_calls: 0, today_agent_calls: 0, models: 0, active_models: 0 })

async function loadOverview() {
  try { Object.assign(overview, await getHistoryOverview()) }
  catch { ElMessage.error('历史概览加载失败') }
}

async function handleTabChange(name) {
  loadedTabs[name] = true
  await nextTick()
}

async function refreshCurrent() {
  refreshing.value = true
  try {
    await Promise.all([loadOverview(), ({ detection: detectionPanel, agent: agentPanel, model: modelPanel })[activeTab.value].value?.refresh?.()])
  } finally { refreshing.value = false }
}

onMounted(loadOverview)
</script>

<style lang="scss" scoped>
.history-page { min-height: 100%; padding: 24px; display: flex; flex-direction: column; gap: 18px; color: $text-primary; background: $bg-color; }
.page-header { padding: 8px 0 14px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.page-header .vp-kicker { margin-bottom: 6px; }
.page-actions { display: flex; align-items: center; flex-shrink: 0; gap: 10px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.summary-grid article { min-width: 0; padding: 17px 18px; display: grid; grid-template-columns: 42px 1fr; align-items: center; gap: 12px; background: $surface-color; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; }
.summary-grid article > span { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 13px; font-size: 19px; }
.summary-grid .detection > span { color: $primary-color; background: $primary-soft; }
.summary-grid .agent > span { color: $secondary-color; background: color-mix(in srgb, $secondary-color 12%, transparent); }
.summary-grid .model > span { color: $info-color; background: var(--vp-info-bg); }
.summary-grid .coverage > span { color: $success-color; background: var(--vp-success-bg); }
.summary-grid div { min-width: 0; display: grid; grid-template-columns: 1fr auto; align-items: baseline; }
.summary-grid small { color: $text-secondary; font-size: 11px; font-weight: 700; }
.summary-grid strong { grid-row: 1 / 3; grid-column: 2; color: $text-primary; font-size: 27px; font-weight: 650; }
.summary-grid p { margin: 3px 0 0; overflow: hidden; color: $text-placeholder; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.history-workspace { min-width: 0; }
.history-tabs :deep(.el-tabs__header) { margin: 0 0 12px; padding: 5px; border: 1px solid $border-color; border-radius: 14px; background: $surface-muted; }
.history-tabs :deep(.el-tabs__nav-wrap::after), .history-tabs :deep(.el-tabs__active-bar) { display: none; }
.history-tabs :deep(.el-tabs__item) { height: 42px; padding: 0 7px; color: $text-secondary; }
.history-tabs :deep(.el-tabs__item.is-active) { color: $text-primary; }
.tab-label { height: 34px; padding: 0 13px; display: inline-flex; align-items: center; gap: 7px; border-radius: 10px; transition: .2s ease; }
.history-tabs :deep(.is-active) .tab-label { color: $primary-color; background: $surface-color; box-shadow: $shadow-sm; }
.tab-label small { min-width: 20px; padding: 2px 6px; border-radius: 999px; color: $text-placeholder; background: $surface-muted; font-size: 9px; text-align: center; }
.history-tabs :deep(.is-active) .tab-label small { color: $primary-color; background: $primary-soft; }
@media (max-width: 1050px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 760px) { .history-page { padding: 16px; }.page-header { align-items: flex-start; flex-direction: column; }.page-actions { width: 100%; justify-content: flex-start; }.summary-grid { grid-template-columns: 1fr; }.history-tabs :deep(.el-tabs__item) { padding: 0 2px; }.tab-label { padding: 0 8px; }.tab-label small { display: none; } }
</style>
