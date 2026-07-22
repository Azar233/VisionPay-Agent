<template>
  <div
    class="vision-character"
    :data-pose="pose"
    :data-projecting="normalizedLoginProgress > 0.01"
    :style="{
      '--vision-progress': normalizedProgress,
      '--login-progress': normalizedLoginProgress,
    }"
    data-mascot-anchor="vision-character"
  >
    <div class="vision-character__halo" aria-hidden="true"></div>
    <div class="vision-character__mascot" role="img" aria-label="Vico mascot">
      <div class="vision-character__shadow" aria-hidden="true"></div>
      <div class="vision-character__sprite" :style="spriteStyle" aria-hidden="true"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import petSprites from '@/assets/pet/visionpay-pet-sprites-v4.png'
import workingPetSprites from '@/assets/pet/visionpay-pet-working-v1.png'

const props = defineProps({
  pose: { type: String, default: 'idle' },
  progress: { type: Number, default: 0 },
  loginProgress: { type: Number, default: 0 },
})
const normalizedProgress = computed(() => Math.min(1, Math.max(0, props.progress || 0)))
const normalizedLoginProgress = computed(() => Math.min(1, Math.max(0, props.loginProgress || 0)))
const spriteStyle = computed(() => ({
  backgroundImage: `url(${props.pose === 'training' ? workingPetSprites : petSprites})`,
  backgroundSize: props.pose === 'training' ? '400% 100%' : '400% 200%',
  backgroundPosition: '0% 0%',
}))
</script>

<style lang="scss" scoped>
.vision-character {
  --login-lift: min(28vh, 260px);
  position: relative;
  display: grid;
  place-items: center;
  width: min(44vw, 430px);
  aspect-ratio: 1;
  transform: translateY(
      calc(var(--vision-progress) * -22px - var(--login-progress) * var(--login-lift))
    )
    scale(calc(1 + var(--vision-progress) * 0.035 - var(--login-progress) * 0.54));
  transform-origin: center;
  will-change: transform;
}
.vision-character__halo {
  position: absolute;
  inset: 7%;
  border: 1px solid color-mix(in srgb, $agent-detection 46%, transparent);
  border-radius: 50%;
  box-shadow:
    0 0 90px color-mix(in srgb, $agent-detection 24%, transparent),
    inset 0 0 65px color-mix(in srgb, $agent-detection 12%, transparent);
  transform: rotate(calc(var(--vision-progress) * 90deg))
    scale(calc(1 + var(--vision-progress) * 0.08));
  will-change: transform;
}
.vision-character__mascot {
  position: relative;
  z-index: 1;
  width: 56%;
  height: 76%;
  filter: drop-shadow(0 20px 28px rgba(0, 0, 0, 0.24));
  animation: mascot-float 3.8s var(--vp-ease-vision-out) infinite;
}
.vision-character__sprite {
  position: absolute;
  inset: 0;
  background-repeat: no-repeat;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
}
.vision-character__shadow {
  position: absolute;
  z-index: -1;
  right: 22%;
  bottom: 5%;
  left: 22%;
  height: 10px;
  border-radius: 50%;
  background: rgba(24, 30, 56, 0.38);
  filter: blur(6px);
}
.vision-character[data-pose='happy'] .vision-character__mascot {
  filter: drop-shadow(0 20px 28px rgba(0, 0, 0, 0.24))
    drop-shadow(0 0 20px color-mix(in srgb, $agent-knowledge 42%, transparent));
}
.vision-character[data-projecting='true'] .vision-character__mascot {
  animation: none;
}
@keyframes mascot-float {
  50% {
    transform: translateY(-14px) rotate(-1.5deg);
  }
}
@media (max-width: 760px) {
  .vision-character {
    width: min(76vw, 340px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .vision-character__mascot {
    animation: none;
  }
}
</style>
