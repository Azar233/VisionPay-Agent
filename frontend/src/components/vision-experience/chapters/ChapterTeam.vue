<template>
  <article class="chapter chapter--split">
    <AgentSystem :progress="progress" :ready="ready" />
    <div>
      <span>03 / I HAVE A TEAM</span>
      <h1 class="team-title">One mission.<br />Five minds.</h1>
      <p>5 个 Agent 协同完成</p>
    </div>
  </article>
</template>

<script setup>
import AgentSystem from '@/components/vision-experience/AgentSystem.vue'

defineProps({ progress: { type: Number, default: 0 }, ready: Boolean })
</script>

<style lang="scss" scoped>
@use './chapter';
.team-title {
  margin: 14px 0 18px;
  font-size: clamp(30px, 3.6vw, 52px);
}
</style>
