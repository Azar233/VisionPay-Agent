<template>
  <div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">
      <el-icon :size="26"><component :is="icon" /></el-icon>
    </div>
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <div v-if="$slots.default" class="empty-state__action">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { Box } from '@element-plus/icons-vue'

defineProps({
  icon: { type: [Object, Function], default: () => Box },
  title: { type: String, required: true },
  description: { type: String, default: '' },
})
</script>

<style lang="scss" scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-state__icon {
  position: relative;
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  margin-bottom: 16px;
  border-radius: 18px;
  color: $primary-color;
  background: $primary-soft;
  border: 1px solid $border-color;

  html.dark & {
    background: rgba(92, 157, 255, 0.1);
    border-color: rgba(140, 180, 255, 0.24);
    box-shadow:
      0 0 32px rgba(92, 157, 255, 0.22),
      inset 0 1px 0 rgba(255, 255, 255, 0.08);
  }
}

.empty-state__title {
  margin: 0;
  color: $text-primary;
  font-size: 15px;
  font-weight: 600;
}

.empty-state__desc {
  max-width: 360px;
  margin: 6px 0 0;
  color: $text-secondary;
  font-size: 13px;
  line-height: 1.6;
}

.empty-state__action {
  margin-top: 18px;
}
</style>
