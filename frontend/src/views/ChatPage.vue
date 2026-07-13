<template>
  <div class="chat-page">
    <section class="chat-shell vp-panel">
      <div class="chat-copy">
        <span class="vp-kicker">Agent Chat</span>
        <h1>智能对话</h1>
        <p>通用多 Agent 编排入口会承接检测、训练和结算分析。</p>
        <el-button type="primary" :icon="Camera" @click="$router.push('/detection')">
          前往商品检测
        </el-button>
      </div>
      <div class="chat-card">
        <header>
          <span><el-icon><ChatDotRound /></el-icon></span>
          <div><strong>VisionPay Assistant</strong><small>Online</small></div>
        </header>
        <main>
          <p class="message user">帮我分析今天的商品识别任务</p>
          <p class="message agent">收到，我会从检测记录、模型指标和低置信度结果中生成摘要。</p>
          <span class="typing"><i></i><i></i><i></i></span>
        </main>
      </div>
    </section>
  </div>
</template>

<script setup>
import { Camera, ChatDotRound } from '@element-plus/icons-vue'
</script>

<style lang="scss" scoped>
.chat-page {
  min-height: 100%;
  padding: 32px;
  background: $bg-color;
}

.chat-shell {
  min-height: calc(100vh - 128px);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 52px;
  padding: 42px;
}

.chat-copy {
  max-width: 420px;

  h1 {
    margin: 10px 0 0;
    font-family: 'Space Grotesk', 'DM Sans', sans-serif;
    font-size: 46px;
    line-height: 1.08;
    color: $text-primary;
  }

  p {
    margin: 14px 0 24px;
    color: $text-secondary;
    font-size: 16px;
    line-height: 1.7;
  }
}

.chat-card {
  width: min(100%, 520px);
  padding: 24px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  box-shadow: $shadow-lg;

  header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid $border-color;
  }

  header > span {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: #fff;
    background: $primary-color;
    font-size: 20px;
  }

  strong,
  small {
    display: block;
  }

  strong {
    color: $text-primary;
    font-weight: 800;
  }

  small {
    margin-top: 2px;
    color: $success-color;
    font-weight: 700;
  }

  main {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding-top: 24px;
  }
}

.message {
  max-width: 78%;
  margin: 0;
  padding: 13px 16px;
  border-radius: $border-radius-md;
  line-height: 1.55;

  &.user {
    align-self: flex-end;
    color: #fff;
    background: $primary-color;
  }

  &.agent {
    background: $surface-muted;
    color: $text-primary;
  }
}

.typing {
  width: fit-content;
  display: inline-flex;
  gap: 5px;
  padding: 12px 16px;
  border-radius: $border-radius-md;
  background: $surface-muted;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $text-secondary;
    animation: chatPulse 1.2s infinite;
  }

  i:nth-child(2) { animation-delay: .16s; }
  i:nth-child(3) { animation-delay: .32s; }
}

@keyframes chatPulse {
  0%, 70%, 100% { opacity: .35; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-2px); }
}

@media (max-width: 900px) {
  .chat-page {
    padding: 20px;
  }

  .chat-shell {
    flex-direction: column;
    align-items: stretch;
    min-height: auto;
    padding: 24px;
  }

  .chat-copy h1 {
    font-size: 36px;
  }
}
</style>
