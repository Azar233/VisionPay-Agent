<template>
  <div class="placeholder-page">
    <div class="placeholder-icon"><el-icon><ChatDotRound /></el-icon></div>
    <h1>智能对话</h1>
    <p>通用对话与多 Agent 编排将在后续阶段实现。</p>
    <el-button type="primary" :icon="Camera" @click="$router.push('/detection')">
      前往商品检测
    </el-button>
  </div>
</template>

<script setup>
import { Camera, ChatDotRound } from '@element-plus/icons-vue'
</script>

<style lang="scss" scoped>
.placeholder-page {
  min-height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #263544;
  background: #f4f6f8;
  text-align: center;
}
.placeholder-icon {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  border: 1px solid #cfd8e1;
  border-radius: 8px;
  color: #1677ff;
  background: #fff;
  font-size: 26px;
}
h1 { margin: 16px 0 7px; font-size: 22px; letter-spacing: 0; }
p { margin: 0 0 20px; color: #718096; font-size: 13px; }
</style>
