<template>
  <Transition name="portal">
    <div v-if="active" class="portal-transition" aria-live="polite">
      <div class="portal-transition__ring"></div>
      <p>进入 VisionPay Workspace</p>
    </div>
  </Transition>
</template>

<script setup>
import { onBeforeUnmount, watch } from 'vue'

const props = defineProps({ active: Boolean })
const emit = defineEmits(['complete'])
let timer
watch(
  () => props.active,
  (active) => {
    window.clearTimeout(timer)
    if (active) timer = window.setTimeout(() => emit('complete'), 1150)
  },
)
onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<style lang="scss" scoped>
.portal-transition {
  position: fixed;
  z-index: 1000;
  inset: 0;
  display: grid;
  place-content: center;
  color: $vj-header-text;
  background: $vj-bg;
}
.portal-transition__ring {
  width: min(58vw, 560px);
  aspect-ratio: 1;
  border: 2px solid $agent-detection;
  border-radius: 50%;
  box-shadow:
    0 0 70px $agent-detection,
    inset 0 0 80px color-mix(in srgb, $agent-detection 40%, transparent);
  animation: portal 1.1s ease-in forwards;
}
.portal-transition p {
  margin: 22px 0 0;
  text-align: center;
  letter-spacing: 0.1em;
}
.portal-enter-active,
.portal-leave-active {
  transition: opacity 0.3s ease;
}
.portal-enter-from,
.portal-leave-to {
  opacity: 0;
}
@keyframes portal {
  to {
    opacity: 0.1;
    transform: scale(3.5);
  }
}
@media (prefers-reduced-motion: reduce) {
  .portal-transition__ring {
    animation-duration: 0.01ms;
  }
}
</style>
