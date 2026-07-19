<template>
  <div class="history-page">
    <section class="summary-grid">
      <button type="button" class="summary-card detection" @click="jumpToTab('detection')"><span><el-icon><View /></el-icon></span><div><small>识别任务</small><strong>{{ overview.detection_tasks }}</strong><p>当前账号累计检测</p></div></button>
      <button type="button" class="summary-card agent" @click="jumpToTab('agent')"><span><el-icon><Connection /></el-icon></span><div><small>Agent 调用</small><strong>{{ overview.agent_calls }}</strong><p>今日 {{ overview.today_agent_calls }} 次</p></div></button>
      <button type="button" class="summary-card model" @click="jumpToTab('model')"><span><el-icon><Cpu /></el-icon></span><div><small>模型版本</small><strong>{{ overview.models }}</strong><p>{{ overview.active_models }} 个处于活动状态</p></div></button>
      <button type="button" class="summary-card coverage"><span><el-icon><Clock /></el-icon></span><div><small>记录范围</small><strong>3</strong><p>检测、Agent 与模型</p></div></button>
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
      <el-tooltip content="刷新当前记录" placement="left" :show-arrow="false">
        <el-button class="tabs-refresh" text :icon="Refresh" :loading="refreshing" aria-label="刷新当前记录" @click="refreshCurrent" />
      </el-tooltip>
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

// 指标卡点击后同步切换下方记录页签。
async function jumpToTab(name) {
  if (activeTab.value === name) return
  activeTab.value = name
  await handleTabChange(name)
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
// 四张独立指标卡，可点击跳转到对应记录页签。
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.summary-card { min-width: 0; padding: 18px 20px; display: grid; grid-template-columns: 44px 1fr; align-items: center; gap: 12px; text-align: left; background: $surface-color; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; cursor: pointer; transition: border-color .2s ease, transform .2s ease, box-shadow .2s ease; }
.summary-card:hover, .summary-card:focus-visible { border-color: $primary-color; box-shadow: $shadow-md; transform: translateY(-1px); }
.summary-card > span { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 13px; font-size: 20px; }
.summary-grid .detection > span { color: $primary-color; background: $primary-soft; }
.summary-grid .agent > span { color: $secondary-color; background: color-mix(in srgb, $secondary-color 12%, transparent); }
.summary-grid .model > span { color: $info-color; background: var(--vp-info-bg); }
.summary-grid .coverage > span { color: $success-color; background: var(--vp-success-bg); }
.summary-card div { min-width: 0; display: grid; grid-template-columns: 1fr auto; align-items: baseline; }
.summary-card small { color: $text-primary; font-size: 17px; font-weight: 700; }
.summary-card strong { grid-row: 1 / 3; grid-column: 2; color: $text-primary; font-size: 28px; font-weight: 650; }
.summary-card p { margin: 4px 0 0; overflow: hidden; color: $text-placeholder; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.history-workspace { position: relative; min-width: 0; }
// 刷新按钮：透明文字钮，锚定在灰条右端内部（卡片内边距 24px + 灰条内缩），与 tab 头同高。
.tabs-refresh { position: absolute; top: 33px; right: 30px; z-index: 5; color: $text-secondary; }
.tabs-refresh:hover, .tabs-refresh:focus-visible { color: $primary-color; }
.history-tabs :deep(.el-tabs__header) { margin: 0 0 12px; padding: 5px; border: 1px solid $border-color; border-radius: 14px; background: $surface-muted; }
.history-tabs :deep(.el-tabs__nav-wrap::after), .history-tabs :deep(.el-tabs__active-bar) { display: none; }
.history-tabs :deep(.el-tabs__item) { height: 42px; padding: 0 7px; color: $text-secondary; }
.history-tabs :deep(.el-tabs__item.is-active) { color: $text-primary; }
.tab-label { height: 34px; padding: 0 13px; display: inline-flex; align-items: center; gap: 7px; border-radius: 10px; transition: .2s ease; }
.history-tabs :deep(.is-active) .tab-label { color: $primary-color; background: $surface-color; box-shadow: $shadow-sm; }
.tab-label small { min-width: 20px; padding: 2px 6px; border-radius: 999px; color: $text-placeholder; background: $surface-muted; font-size: 9px; text-align: center; }
.history-tabs :deep(.is-active) .tab-label small { color: $primary-color; background: $primary-soft; }
@media (max-width: 1050px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 760px) { .history-page { padding: 16px; }.summary-grid { grid-template-columns: 1fr; }.history-tabs :deep(.el-tabs__item) { padding: 0 2px; }.tab-label { padding: 0 8px; }.tab-label small { display: none; } }
</style>
