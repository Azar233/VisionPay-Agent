<template>
  <section class="knowledge-sources-card" :class="{ empty: !sources.length }">
    <button
      class="sources-summary"
      type="button"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="sources-mark"><el-icon><Collection /></el-icon></span>
      <span class="sources-heading">
        <strong>{{ sources.length ? `参考知识 ${sources.length}` : '未找到可靠参考资料' }}</strong>
        <small>{{ summaryText }}</small>
      </span>
      <span v-if="sources.length" class="source-domains">
        {{ domainSummary }}
      </span>
      <el-icon class="expand-icon" :class="{ expanded }"><ArrowDown /></el-icon>
    </button>

    <div v-show="expanded" class="sources-body">
      <div v-if="rewrittenQuery" class="retrieval-query">
        <span>实际检索问题</span>
        <p>{{ rewrittenQuery }}</p>
      </div>
      <ol v-if="sources.length" class="source-list">
        <li v-for="source in sources" :key="`${source.collection}:${source.id}`">
          <div class="source-index">{{ source.rank || 1 }}</div>
          <div class="source-copy">
            <div class="source-title">
              <strong>{{ source.title || source.source }}</strong>
              <span>{{ collectionLabel(source.collection) }}</span>
              <em>{{ similarityText(source.similarity) }}</em>
            </div>
            <small>{{ source.source }}</small>
            <p v-if="source.excerpt">{{ source.excerpt }}</p>
          </div>
        </li>
      </ol>
      <p v-else class="empty-copy">
        本轮已经执行检索，但没有片段达到相似度阈值。回答不应将模型推断表述为平台事实。
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowDown, Collection } from '@element-plus/icons-vue'

const props = defineProps({
  payload: { type: Object, required: true },
})

const expanded = ref(false)
const sources = computed(() => Array.isArray(props.payload?.sources) ? props.payload.sources : [])
const retrievals = computed(() => Array.isArray(props.payload?.retrievals) ? props.payload.retrievals : [])
const rewrittenQuery = computed(() => (
  retrievals.value.find((item) => item?.rewritten_query)?.rewritten_query || ''
))
const domainSummary = computed(() => {
  const domains = [...new Set(sources.value.map((item) => item.domain).filter(Boolean))]
  return domains.slice(0, 2).join(' · ') || '通用'
})
const summaryText = computed(() => {
  if (!sources.value.length) return '已完成强制检索'
  const collections = new Set(sources.value.map((item) => item.collection))
  return collections.has('fault_cases') ? '业务知识与故障案例' : '业务知识库'
})

function collectionLabel(value) {
  return value === 'fault_cases' ? '故障案例' : '知识文档'
}
function similarityText(value) {
  const score = Number(value)
  return Number.isFinite(score) ? `${Math.round(score * 100)}%` : '—'
}
</script>

<style lang="scss" scoped>
.knowledge-sources-card {
  width: min(100%, 720px);
  margin-top: 14px;
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: 13px;
  background: color-mix(in srgb, $surface-muted 72%, transparent);
}
.sources-summary {
  width: 100%;
  min-height: 58px;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 10px;
  padding: 10px 13px;
  border: 0;
  color: $text-primary;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.sources-summary:hover { background: color-mix(in srgb, $text-primary 4%, transparent); }
.sources-mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, $success-color 24%, $border-color);
  border-radius: 9px;
  color: $success-color;
  background: color-mix(in srgb, $success-color 8%, transparent);
}
.sources-heading { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.sources-heading strong { font-size: 12px; font-weight: 680; }
.sources-heading small { color: $text-placeholder; font-size: 9px; }
.source-domains {
  padding: 3px 7px;
  border: 1px solid $border-color;
  border-radius: 999px;
  color: $text-secondary;
  font-size: 9px;
  text-transform: capitalize;
}
.expand-icon { color: $text-placeholder; transition: transform .18s ease; }
.expand-icon.expanded { transform: rotate(180deg); }
.sources-body { padding: 0 13px 13px; border-top: 1px solid $border-color; }
.retrieval-query { padding: 11px 0 9px; }
.retrieval-query span { color: $text-placeholder; font-size: 9px; font-weight: 650; }
.retrieval-query p { margin: 4px 0 0; color: $text-secondary; font-size: 10px; line-height: 1.55; }
.source-list { display: flex; flex-direction: column; gap: 7px; margin: 0; padding: 0; list-style: none; }
.source-list li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  padding: 10px;
  border: 1px solid $border-color;
  border-radius: 10px;
  background: $surface-color;
}
.source-index {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  color: $text-secondary;
  background: $surface-muted;
  font-size: 9px;
  font-weight: 700;
}
.source-copy { min-width: 0; }
.source-title { display: flex; align-items: center; gap: 6px; }
.source-title strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 650; text-transform: capitalize; }
.source-title span { flex: 0 0 auto; color: $success-color; font-size: 8px; }
.source-title em { margin-left: auto; color: $text-placeholder; font-size: 9px; font-style: normal; font-variant-numeric: tabular-nums; }
.source-copy > small { display: block; margin-top: 3px; overflow: hidden; color: $text-placeholder; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.source-copy > p { margin: 7px 0 0; color: $text-secondary; font-size: 10px; line-height: 1.6; }
.empty .sources-mark { color: $text-placeholder; border-color: $border-color; background: transparent; }
.empty-copy { margin: 11px 0 0; color: $text-secondary; font-size: 10px; line-height: 1.6; }

:global(html.dark) .knowledge-sources-card { background: rgba(255,255,255,.025); border-color: rgba(255,255,255,.1); }
:global(html.dark) .sources-summary:hover { background: rgba(255,255,255,.035); }
:global(html.dark) .sources-body,
:global(html.dark) .source-list li { border-color: rgba(255,255,255,.1); }
:global(html.dark) .source-list li { background: rgba(255,255,255,.035); }
:global(html.dark) .source-index { background: rgba(255,255,255,.06); }

@media (max-width: 640px) {
  .sources-summary { grid-template-columns: 32px minmax(0, 1fr) 18px; }
  .source-domains { display: none; }
}
</style>
