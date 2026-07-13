<template>
  <div class="dashboard-page">
    <section class="hero-panel">
      <span class="vp-kicker">Analytics</span>
      <h1>数据看板</h1>
      <p>汇总商品识别、训练任务和智能体运行状态，后续可接入实时指标。</p>
    </section>

    <section class="metric-grid">
      <article v-for="item in metrics" :key="item.label" class="metric-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.note }}</small>
      </article>
    </section>

    <section class="preview-grid">
      <article class="vp-panel trend-panel">
        <div class="panel-title">识别趋势</div>
        <div class="bars">
          <span v-for="item in bars" :key="item" :style="{ height: `${item}%` }"></span>
        </div>
      </article>
      <article class="vp-panel insight-panel">
        <div class="panel-title">Agent Insight</div>
        <p>商品检测、训练监控和结算分析会在这里形成统一运营视图。</p>
        <el-button type="primary" plain @click="$router.push('/detection')">进入检测工作台</el-button>
      </article>
    </section>
  </div>
</template>

<script setup>
const metrics = [
  { label: '检测任务', value: '--', note: '等待接入历史统计' },
  { label: '训练任务', value: '--', note: 'YOLOv11 pipeline' },
  { label: '平均置信度', value: '--', note: '按商品类别聚合' },
]
const bars = [36, 52, 44, 70, 58, 82, 66, 74, 90, 62, 78, 88]
</script>

<style lang="scss" scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 100%;
  padding: 32px;
  background: $bg-color;
}

.hero-panel {
  padding: 34px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  box-shadow: $shadow-sm;

  h1 {
    margin: 10px 0 0;
    font-family: 'Space Grotesk', 'DM Sans', sans-serif;
    font-size: 42px;
    line-height: 1.08;
    color: $text-primary;
  }

  p {
    max-width: 620px;
    margin: 12px 0 0;
    color: $text-secondary;
    font-size: 16px;
    line-height: 1.7;
  }
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  min-height: 132px;
  padding: 20px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  box-shadow: $shadow-sm;

  span,
  small {
    color: $text-secondary;
  }

  strong {
    display: block;
    margin: 18px 0 8px;
    color: $text-primary;
    font-size: 34px;
  }
}

.preview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr);
  gap: 14px;
}

.trend-panel,
.insight-panel {
  padding: 22px;
}

.panel-title {
  color: $text-primary;
  font-weight: 800;
}

.bars {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  align-items: end;
  gap: 8px;
  height: 230px;
  margin-top: 24px;
  padding: 18px;
  border-radius: $border-radius-md;
  background: $surface-muted;

  span {
    min-height: 24px;
    border-radius: 6px 6px 0 0;
    background: linear-gradient(180deg, $secondary-color, $primary-color);
  }
}

.insight-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;

  p {
    margin: 18px 0;
    color: $text-secondary;
    line-height: 1.7;
  }
}

@media (max-width: 900px) {
  .dashboard-page {
    padding: 20px;
  }

  .metric-grid,
  .preview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
