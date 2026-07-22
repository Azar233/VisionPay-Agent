<template>
  <button class="skip-intro" type="button" @click="$emit('skip')">跳过动画 <span>→</span></button>
</template>

<script setup>
defineEmits(['skip'])
</script>

<style lang="scss" scoped>
.skip-intro {
  position: fixed;
  z-index: 8;
  right: 24px;
  bottom: 24px;
  padding: 9px 13px;
  border: 1px solid color-mix(in srgb, $agent-detection 35%, $border-color);
  border-radius: 999px;
  color: $text-secondary;
  background: color-mix(in srgb, $surface-color 78%, transparent);
  cursor: pointer;
  backdrop-filter: blur(14px);
}
.skip-intro:hover {
  color: $agent-detection;
}
</style>
