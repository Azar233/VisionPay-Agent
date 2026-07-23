<template>
  <div class="history-page">
    <section class="summary-hero vp-glass">
      <button type="button" class="summary-item" @click="jumpToTab('detection')">
        <span class="summary-icon"
          ><el-icon><View /></el-icon
        ></span>
        <span class="summary-text">
          <small>识别任务</small>
          <strong class="vp-num">{{ Math.round(detectionCount) }}</strong>
          <p>当前账号累计检测</p>
        </span>
      </button>
      <button type="button" class="summary-item" @click="jumpToTab('agent')">
        <span class="summary-icon"
          ><el-icon><Connection /></el-icon
        ></span>
        <span class="summary-text">
          <small>Agent 调用</small>
          <strong class="vp-num">{{ Math.round(agentCount) }}</strong>
          <p>今日 {{ overview.today_agent_calls }} 次</p>
        </span>
      </button>
      <button type="button" class="summary-item" @click="jumpToTab('model')">
        <span class="summary-icon"
          ><el-icon><Cpu /></el-icon
        ></span>
        <span class="summary-text">
          <small>模型版本</small>
          <strong class="vp-num">{{ Math.round(modelCount) }}</strong>
          <p>{{ overview.active_models }} 个处于活动状态</p>
        </span>
      </button>
    </section>

    <section class="history-workspace card-container">
      <el-tabs v-model="activeTab" class="history-tabs" @tab-change="handleTabChange">
        <el-tab-pane name="detection">
          <template #label
            ><span class="tab-label"
              ><el-icon><View /></el-icon><span>识别记录</span></span
            ></template
          >
          <DetectionHistoryPanel ref="detectionPanel" @changed="loadOverview" />
        </el-tab-pane>
        <el-tab-pane name="agent">
          <template #label
            ><span class="tab-label"
              ><el-icon><Connection /></el-icon><span>Agent 调用</span></span
            ></template
          >
          <AgentHistoryPanel v-if="loadedTabs.agent" ref="agentPanel" />
        </el-tab-pane>
        <el-tab-pane name="model">
          <template #label
            ><span class="tab-label"
              ><el-icon><Cpu /></el-icon><span>模型历史</span></span
            ></template
          >
          <ModelHistoryPanel v-if="loadedTabs.model" ref="modelPanel" />
        </el-tab-pane>
      </el-tabs>
      <el-tooltip content="刷新当前记录" placement="left" :show-arrow="false">
        <el-button
          class="tabs-refresh"
          text
          :icon="Refresh"
          :loading="refreshing"
          aria-label="刷新当前记录"
          @click="refreshCurrent"
        />
      </el-tooltip>
    </section>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { Connection, Cpu, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentHistoryPanel from '@/components/history/AgentHistoryPanel.vue'
import DetectionHistoryPanel from '@/components/history/DetectionHistoryPanel.vue'
import ModelHistoryPanel from '@/components/history/ModelHistoryPanel.vue'
import { getHistoryOverview } from '@/api/history'
import { useCountUp } from '@/composables/useCountUp'

const activeTab = ref('detection')
const refreshing = ref(false)
const detectionPanel = ref(null)
const agentPanel = ref(null)
const modelPanel = ref(null)
const loadedTabs = reactive({ detection: true, agent: false, model: false })
const overview = reactive({
  detection_tasks: 0,
  agent_calls: 0,
  today_agent_calls: 0,
  models: 0,
  active_models: 0,
})

// 概览带数字滚动动画：概览刷新后自动滚到新值，prefers-reduced-motion 下直接落终值。
const detectionCount = useCountUp(() => overview.detection_tasks)
const agentCount = useCountUp(() => overview.agent_calls)
const modelCount = useCountUp(() => overview.models)

async function loadOverview() {
  try {
    Object.assign(overview, await getHistoryOverview())
  } catch {
    ElMessage.error('历史概览加载失败')
  }
}

async function handleTabChange(name) {
  loadedTabs[name] = true
  await nextTick()
}

// 概览带统计项点击后同步切换下方记录页签。
async function jumpToTab(name) {
  if (activeTab.value === name) return
  activeTab.value = name
  await handleTabChange(name)
}

async function refreshCurrent() {
  refreshing.value = true
  try {
    await Promise.all([
      loadOverview(),
      { detection: detectionPanel, agent: agentPanel, model: modelPanel }[
        activeTab.value
      ].value?.refresh?.(),
    ])
  } finally {
    refreshing.value = false
  }
}

onMounted(loadOverview)
</script>

<style lang="scss" scoped>
.history-page {
  min-height: 100%;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: $text-primary;
  background: $bg-color;
}
// 通栏 hero 概览带：玻璃拟态卡片，深色下叠一层微弱品牌渐变底纹；
// 内部统计项横向排布、1px 分隔线相隔，点击跳转对应记录页签。
.summary-hero {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  align-items: stretch;
  padding: 10px;

  html.dark & {
    background:
      linear-gradient(
        135deg,
        color-mix(in srgb, var(--vp-primary) 9%, transparent),
        color-mix(in srgb, var(--vp-accent-cyan) 6%, transparent)
      ),
      var(--vp-surface);
  }
}
.summary-item {
  min-width: 0;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 14px;
  text-align: left;
  color: inherit;
  background: transparent;
  border: 0;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    transform 0.2s ease;
}
.summary-item + .summary-item {
  border-left: 1px solid $border-color;
}
.summary-item:hover,
.summary-item:focus-visible {
  background: $primary-soft;
  transform: translateY(-1px);
}
// 统一主色强调：品牌渐变图标底，深色下加品牌光晕。
.summary-icon {
  flex: none;
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  font-size: 20px;
  background: var(--vp-brand-gradient);

  html.dark & {
    box-shadow: 0 0 14px var(--vp-border-glow);
  }
}
.summary-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.summary-text small {
  color: $text-secondary;
  font-size: 12px;
  font-weight: 500;
}
.summary-text strong {
  margin: 2px 0;
  color: $text-primary;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
}
.summary-text p {
  margin: 0;
  overflow: hidden;
  color: $text-secondary;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-workspace {
  position: relative;
  min-width: 0;
}
// 刷新按钮：透明文字钮，锚定在灰条右端内部（卡片内边距 24px + 灰条内缩），与 tab 头同高。
.tabs-refresh {
  position: absolute;
  top: 33px;
  right: 30px;
  z-index: 5;
  color: $text-secondary;
}
.tabs-refresh:hover,
.tabs-refresh:focus-visible {
  color: $primary-color;
}
.history-tabs :deep(.el-tabs__header) {
  margin: 0 0 12px;
  padding: 5px;
  border: 1px solid $border-color;
  border-radius: 14px;
  background: $surface-muted;
}
.history-tabs :deep(.el-tabs__nav-wrap::after),
.history-tabs :deep(.el-tabs__active-bar) {
  display: none;
}
.history-tabs :deep(.el-tabs__item) {
  height: 42px;
  padding: 0 7px;
  color: $text-secondary;
}
.history-tabs :deep(.el-tabs__item.is-active) {
  color: $text-primary;
}
.tab-label {
  height: 34px;
  padding: 0 13px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 10px;
  transition: 0.2s ease;
}
.history-tabs :deep(.is-active) .tab-label {
  color: $primary-color;
  background: $surface-color;
  box-shadow: $shadow-sm;
}
@media (max-width: 760px) {
  .history-page {
    padding: 16px;
  }
  .summary-hero {
    grid-template-columns: 1fr;
  }
  .summary-item + .summary-item {
    border-top: 1px solid $border-color;
    border-left: 0;
  }
  .history-tabs :deep(.el-tabs__item) {
    padding: 0 2px;
  }
  .tab-label {
    padding: 0 8px;
  }
}
</style>
