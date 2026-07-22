<template>
  <span :class="['agent-glyph', agent.name]" :aria-label="agent.label">
    <el-icon><component :is="agent.icon" /></el-icon>
  </span>
</template>

<script setup>
defineProps({ agent: { type: Object, required: true } })
</script>

<style lang="scss" scoped>
.agent-glyph {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid currentColor;
  border-radius: 11px;
  background: color-mix(in srgb, currentColor 13%, transparent);
}
.detection {
  color: $agent-detection;
}
.dataset {
  color: $agent-dataset;
}
.training {
  color: $agent-training;
}
.catalog {
  color: $agent-catalog;
}
.knowledge {
  color: $agent-knowledge;
}
</style>
