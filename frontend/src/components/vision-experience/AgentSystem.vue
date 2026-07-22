<template>
  <div ref="systemRoot" class="agent-system" role="list" aria-label="VisionPay Agent 团队">
    <div class="agent-system__rail" aria-hidden="true"></div>
    <i
      :class="['agent-system__task', { 'is-ready': taskReady }]"
      :style="{ top: `${taskTop}px` }"
      aria-hidden="true"
    ></i>
    <article
      v-for="(agent, index) in agents"
      :key="agent.name"
      role="listitem"
      :class="[
        agent.name,
        { active: index === activeIndex, revealed: progress >= index / agents.length || ready },
      ]"
      :style="{ '--index': index }"
    >
      <AgentGlyph :agent="agent" />
      <div>
        <strong>{{ agent.label }}</strong>
        <small>{{ agent.description }}</small>
      </div>
      <em v-if="index === activeIndex" class="agent-system__tag">进行中</em>
    </article>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AGENT_TEAM } from '@/constants/agentTeam'
import AgentGlyph from './AgentGlyph.vue'

const props = defineProps({
  progress: { type: Number, default: 0 },
  ready: { type: Boolean, default: false },
})
const agents = AGENT_TEAM
const systemRoot = ref(null)
const taskTop = ref(0)
const taskReady = ref(false)
let taskFrame = 0
let taskResizeObserver
const activeIndex = computed(() =>
  Math.min(agents.length - 1, Math.floor(Math.max(0, props.progress) * agents.length)),
)

function syncTaskPosition() {
  taskFrame = 0
  const activeCard = systemRoot.value?.querySelectorAll('article')[activeIndex.value]
  if (!activeCard) return

  taskTop.value = activeCard.offsetTop + activeCard.offsetHeight / 2
  taskReady.value = true
}

function scheduleTaskPosition() {
  if (taskFrame) cancelAnimationFrame(taskFrame)
  taskFrame = requestAnimationFrame(syncTaskPosition)
}

watch(activeIndex, scheduleTaskPosition, { flush: 'post' })

onMounted(() => {
  scheduleTaskPosition()
  taskResizeObserver = new ResizeObserver(scheduleTaskPosition)
  if (systemRoot.value) taskResizeObserver.observe(systemRoot.value)
})

onBeforeUnmount(() => {
  if (taskFrame) cancelAnimationFrame(taskFrame)
  taskResizeObserver?.disconnect()
})
</script>

<style lang="scss" scoped>
.agent-system {
  position: relative;
  display: grid;
  gap: 10px;
  width: 100%;
  max-width: 380px;
  min-width: 0;
  padding-left: 30px;
}
.agent-system__rail {
  position: absolute;
  top: 6px;
  bottom: 6px;
  left: 13px;
  width: 2px;
  background: linear-gradient(
    to bottom,
    transparent,
    $vj-agent-rail 8%,
    $vj-agent-rail 92%,
    transparent
  );
}
.agent-system__task {
  position: absolute;
  z-index: 2;
  left: 14px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: $vj-dot;
  box-shadow:
    0 0 16px $vj-dot,
    0 0 30px $agent-detection;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.65);
  transition:
    opacity 0.2s ease,
    transform 0.3s var(--vp-ease-vision-out);
  pointer-events: none;
}
.agent-system__task.is-ready {
  opacity: 1;
  transform: translate(-50%, -50%) scale(1);
}
.agent-system article {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid color-mix(in srgb, currentColor 32%, transparent);
  border-radius: 14px;
  color: $vj-agent-panel-text;
  background: $vj-agent-panel-bg;
  opacity: 0;
  transform: translateX(-18px);
  transition:
    opacity 0.34s ease calc(var(--index) * 90ms),
    transform 0.42s var(--vp-ease-vision-out) calc(var(--index) * 90ms),
    color 0.3s ease,
    box-shadow 0.3s ease;
}
.agent-system article.revealed {
  opacity: 1;
  transform: translateX(0);
}
.agent-system article.active {
  color: $vj-agent-panel-text-active;
  border-color: currentColor;
  box-shadow:
    0 0 22px -4px currentColor,
    inset 0 0 0 1px color-mix(in srgb, currentColor 45%, transparent);
}
.agent-system strong,
.agent-system small {
  display: block;
}
.agent-system strong {
  font-size: 13px;
  letter-spacing: 0.01em;
}
.agent-system small {
  margin-top: 2px;
  color: inherit;
  opacity: 0.82;
  font-size: 11px;
}
.agent-system__tag {
  margin-left: auto;
  padding: 3px 8px;
  border-radius: 999px;
  color: #050716;
  background: #fff;
  font-size: 9px;
  font-style: normal;
  font-weight: 800;
  letter-spacing: 0.06em;
  white-space: nowrap;
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
@media (max-width: 760px) {
  .agent-system {
    width: 100%;
    padding-left: 26px;
  }
  .agent-system article {
    padding: 9px 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .agent-system article {
    transition: opacity 0.2s linear;
    transform: none;
  }
  .agent-system__task {
    transition: none;
  }
}
</style>
