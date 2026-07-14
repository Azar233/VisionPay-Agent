<template>
  <div class="dashboard-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <span class="vp-kicker">VisionPay Overview</span>
        <h1>零售视觉，<br />一目了然。</h1>
        <p>在一个安静、清晰的视图中掌握商品识别、训练任务与智能体运行状态。</p>
        <div class="hero-actions">
          <el-button type="primary" @click="$router.push('/detection')">开始商品检测</el-button>
          <router-link to="/training">查看模型训练 <span>›</span></router-link>
        </div>
      </div>
      <div class="hero-visual" aria-hidden="true">
        <div class="visual-orbit orbit-one"></div>
        <div class="visual-orbit orbit-two"></div>
        <div class="visual-mark"><img src="/favicon.svg" alt="" /></div>
        <span class="signal signal-one"></span>
        <span class="signal signal-two"></span>
        <span class="signal signal-three"></span>
      </div>
    </section>

    <section class="metric-grid" aria-label="核心指标">
      <article v-for="item in metrics" :key="item.label" class="metric-card">
        <div class="metric-icon"><el-icon><component :is="item.icon" /></el-icon></div>
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.note }}</small>
      </article>
    </section>

    <section class="insight-panel">
      <div>
        <span class="vp-kicker">Today</span>
        <h2>智能分析已准备就绪</h2>
        <p>上传商品图片后，系统会在这里逐步形成识别趋势、价格汇总与低置信度提醒。</p>
      </div>
      <div class="readiness"><span></span><strong>系统就绪</strong><small>等待新任务</small></div>
    </section>
  </div>
</template>

<script setup>
import { Camera, Cpu, TrendCharts } from '@element-plus/icons-vue'

const metrics = [
  { label: '检测任务', value: '—', note: '等待首次识别', icon: Camera },
  { label: '训练任务', value: '—', note: 'YOLOv11 pipeline', icon: Cpu },
  { label: '平均置信度', value: '—', note: '按商品类别汇总', icon: TrendCharts },
]
</script>

<style lang="scss" scoped>
.dashboard-page { min-height: 100%; padding: 32px; display: flex; flex-direction: column; gap: 24px; background: transparent; }

.hero-panel {
  position: relative;
  min-height: 390px;
  padding: clamp(40px, 6vw, 72px);
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(300px, .9fr);
  align-items: center;
  gap: 48px;
  overflow: hidden;
  background: rgba(255, 255, 255, .82);
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  box-shadow: 0 18px 55px rgba(0, 0, 0, .055);
  backdrop-filter: blur(24px) saturate(130%);
}

.hero-copy { position: relative; z-index: 2; }
.hero-copy h1 { margin: 14px 0 0; color: $text-primary; font-size: clamp(44px, 6vw, 68px); font-weight: 600; line-height: 1.02; letter-spacing: -.06em; }
.hero-copy p { max-width: 590px; margin: 20px 0 0; color: $text-secondary; font-size: 17px; line-height: 1.65; }
.hero-actions { margin-top: 30px; display: flex; align-items: center; gap: 22px; }
.hero-actions .el-button { min-height: 48px; padding-inline: 24px; }
.hero-actions a { color: $primary-color; font-size: 15px; font-weight: 500; }
.hero-actions a span { display: inline-block; margin-left: 3px; font-size: 20px; transition: transform .2s ease; }
.hero-actions a:hover span { transform: translateX(3px); }

.hero-visual { position: relative; min-height: 260px; display: grid; place-items: center; }
.visual-mark { z-index: 2; width: 96px; height: 96px; display: grid; place-items: center; border-radius: 28px; background: linear-gradient(145deg, #1688f8, #0068d4); box-shadow: 0 28px 70px rgba(0, 113, 227, .28), inset 0 1px rgba(255,255,255,.38); }
.visual-mark img { width: 54px; height: 54px; }
.visual-orbit { position: absolute; border: 1px solid rgba(0, 113, 227, .14); border-radius: 50%; }
.orbit-one { width: 210px; height: 210px; }
.orbit-two { width: 300px; height: 300px; border-color: rgba(0, 113, 227, .08); }
.signal { position: absolute; width: 10px; height: 10px; border: 3px solid #fff; border-radius: 50%; background: $primary-color; box-shadow: 0 4px 12px rgba(0, 113, 227, .28); }
.signal-one { top: 24px; right: 28%; }.signal-two { bottom: 42px; left: 21%; }.signal-three { right: 16%; bottom: 26%; width: 7px; height: 7px; }

.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.metric-card { min-height: 170px; padding: 24px; display: grid; grid-template-columns: 40px 1fr; grid-template-rows: auto auto auto; align-items: center; column-gap: 14px; background: rgba(255,255,255,.76); border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: $shadow-sm; transition: transform .25s ease, box-shadow .25s ease; }
.metric-card:hover { transform: translateY(-2px); box-shadow: $shadow-md; }
.metric-icon { grid-row: 1; width: 40px; height: 40px; display: grid; place-items: center; color: $primary-color; background: $primary-soft; border-radius: 12px; font-size: 18px; }
.metric-card > span { color: $text-secondary; font-size: 13px; }
.metric-card strong { grid-column: 1 / -1; margin-top: 16px; color: $text-primary; font-size: 34px; font-weight: 600; letter-spacing: -.04em; }
.metric-card small { grid-column: 1 / -1; margin-top: 5px; color: $text-placeholder; }

.insight-panel { padding: 32px; display: flex; align-items: center; justify-content: space-between; gap: 24px; background: rgba(255,255,255,.76); border: 1px solid $border-color; border-radius: $border-radius-md; }
.insight-panel h2 { margin: 8px 0 0; font-size: 24px; font-weight: 600; letter-spacing: -.025em; }
.insight-panel p { max-width: 650px; margin: 9px 0 0; color: $text-secondary; line-height: 1.6; }
.readiness { min-width: 160px; display: grid; grid-template-columns: 9px 1fr; gap: 3px 9px; align-items: center; }
.readiness > span { width: 9px; height: 9px; grid-row: 1 / 3; border-radius: 50%; background: $success-color; box-shadow: 0 0 0 5px rgba(36,138,61,.1); }
.readiness strong { font-size: 14px; font-weight: 600; }.readiness small { color: $text-secondary; }

@media (prefers-reduced-motion: no-preference) { .visual-orbit { animation: breathe 4s ease-in-out infinite; } .orbit-two { animation-delay: -2s; } @keyframes breathe { 50% { transform: scale(1.035); opacity: .65; } } }
@media (max-width: 980px) { .hero-panel { grid-template-columns: 1fr; }.hero-visual { display: none; } }
@media (max-width: 760px) { .dashboard-page { padding: 12px; gap: 12px; }.hero-panel { min-height: auto; padding: 36px 24px; }.hero-copy h1 { font-size: 42px; }.metric-grid { grid-template-columns: 1fr; }.insight-panel { align-items: flex-start; flex-direction: column; } }
</style>
