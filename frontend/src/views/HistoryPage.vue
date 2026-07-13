<template>
  <div class="history-page">
    <section class="history-hero">
      <span class="vp-kicker">Records</span>
      <h1>历史记录</h1>
      <p>保留检测会话、训练结果和后续结算记录的统一入口。</p>
    </section>

    <section class="timeline vp-panel">
      <article v-for="item in items" :key="item.title" class="timeline-item">
        <span class="dot"></span>
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
        </div>
        <small>{{ item.status }}</small>
      </article>
    </section>
  </div>
</template>

<script setup>
const items = [
  { title: '商品检测记录', desc: '批量图片、单图和 ZIP 检测结果会在此归档。', status: '准备中' },
  { title: '训练结果归档', desc: '每次 YOLOv11 训练的 metrics 与 results.csv 会关联到任务。', status: '已接入' },
  { title: '结算清单历史', desc: '后续自动结算清单将与识别任务保持关联。', status: '规划中' },
]
</script>

<style lang="scss" scoped>
.history-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 100%;
  padding: 32px;
  background: $bg-color;
}

.history-hero {
  padding: 34px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  box-shadow: $shadow-sm;

  h1 {
    margin: 10px 0 0;
    font-family: 'Space Grotesk', 'DM Sans', sans-serif;
    font-size: 42px;
    color: $text-primary;
  }

  p {
    margin: 12px 0 0;
    color: $text-secondary;
    font-size: 16px;
  }
}

.timeline {
  padding: 10px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  padding: 18px;
  border-bottom: 1px solid $border-color;

  &:last-child {
    border-bottom: 0;
  }

  strong {
    color: $text-primary;
    font-size: 16px;
  }

  p {
    margin: 6px 0 0;
    color: $text-secondary;
    line-height: 1.6;
  }

  small {
    padding: 5px 10px;
    border-radius: 999px;
    color: $primary-color;
    background: $primary-soft;
    font-weight: 800;
  }
}

.dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 50%;
  background: $primary-color;
  box-shadow: 0 0 0 5px $primary-soft;
}

@media (max-width: 760px) {
  .history-page {
    padding: 20px;
  }

  .timeline-item {
    grid-template-columns: 16px minmax(0, 1fr);

    small {
      grid-column: 2;
      width: fit-content;
    }
  }
}
</style>
