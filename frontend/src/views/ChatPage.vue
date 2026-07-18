<template>
  <div class="agent-chat-page" @dragover.prevent @drop.prevent="handleDrop">
    <div :class="['chat-layout', { 'sessions-collapsed': sessionsCollapsed, 'insights-collapsed': insightsCollapsed }]">
      <aside class="session-panel" :aria-hidden="sessionsCollapsed">
        <div class="sidebar-toolbar">
          <el-button class="new-chat" type="primary" :icon="Plus" @click="createNewChat">
            <span>新建对话</span>
          </el-button>
          <el-tooltip content="收起历史对话" placement="right" :show-arrow="false">
            <el-button class="panel-toggle" :icon="DArrowLeft" circle aria-label="收起历史对话" @click="sessionsCollapsed = true" />
          </el-tooltip>
        </div>
        <div class="panel-title"><span>最近对话</span><el-button text :icon="Refresh" :loading="sessionLoading" @click="loadSessions" /></div>
        <div class="session-list" v-loading="sessionLoading">
          <button
            v-for="session in agentStore.sessions"
            :key="session.session_uuid"
            type="button"
            :class="['session-item', { active: session.session_uuid === agentStore.currentSessionId }]"
            @click="openSession(session.session_uuid)"
          >
            <span class="session-icon"><el-icon><ChatDotRound /></el-icon></span>
            <span class="session-copy"><strong>{{ session.title }}</strong><small>{{ formatTime(session.last_message_at || session.created_at) }}</small></span>
            <i class="delete-session" role="button" tabindex="0" @click.stop="removeSession(session)" @keydown.enter.stop="removeSession(session)"><el-icon><Delete /></el-icon></i>
          </button>
          <div v-if="!sessionLoading && !agentStore.sessions.length" class="session-empty">还没有对话记录</div>
        </div>
      </aside>

      <main :class="['conversation-panel', { 'has-floating-controls': sessionsCollapsed || insightsCollapsed }]">
        <div v-if="sessionsCollapsed || insightsCollapsed" class="floating-panel-controls" aria-label="侧栏快捷操作">
          <div v-if="sessionsCollapsed" class="floating-control-capsule floating-control-capsule--left">
            <el-tooltip content="展开历史对话" placement="bottom" :show-arrow="false">
              <el-button class="floating-control-button" text :icon="DArrowRight" aria-label="展开历史对话" @click="sessionsCollapsed = false" />
            </el-tooltip>
            <span class="floating-control-divider" aria-hidden="true"></span>
            <el-button class="floating-control-button" text :icon="Plus" aria-label="新建对话" @click="createNewChat" />
          </div>
          <div v-if="insightsCollapsed" class="floating-control-capsule floating-control-capsule--right">
            <el-tooltip content="展开右侧设置" placement="bottom" :show-arrow="false">
              <el-button class="floating-control-button" text :icon="DArrowLeft" aria-label="展开右侧设置" @click="insightsCollapsed = false" />
            </el-tooltip>
          </div>
        </div>
        <div ref="messageListRef" class="message-list">
          <section
            v-if="!agentStore.messages.length"
            :key="`welcome-${newChatViewKey}`"
            class="welcome-state"
          >
            <div class="welcome-mark" aria-hidden="true"><el-icon><Connection /></el-icon></div>
            <span>管理工作区</span>
            <h2>今天想处理什么？</h2>
            <p>描述你的目标，我会选择合适的工具。涉及数据写入或模型变更时，会先请你确认。</p>
            <div class="quick-grid">
              <button v-for="item in quickPrompts" :key="item.title" type="button" @click="inputText = item.prompt">
                <span :class="item.tone"><el-icon><component :is="item.icon" /></el-icon></span>
                <strong>{{ item.title }}</strong><small>{{ item.description }}</small>
                <el-icon class="quick-arrow"><ArrowRight /></el-icon>
              </button>
            </div>
          </section>

          <article v-for="(message, index) in agentStore.messages" :key="message.id || index" :class="['message-row', message.role]">
            <div class="message-column">
              <div v-if="message.role === 'assistant'" class="agent-activity">
                <span :class="['agent-pill', message.agent || 'detection']"><el-icon><Cpu /></el-icon>{{ agentName(message.agent) }}</span>
                <template v-if="message.tool">
                  <i></i>
                  <span class="tool-state"><el-icon><Operation /></el-icon><small>{{ toolPrefix(message.tool) }}</small>{{ toolName(message.tool) }}</span>
                </template>
                <span v-else-if="message.loading" class="activity-status">正在处理</span>
              </div>
              <div class="message-bubble">
                <div v-if="message.content" class="message-content" v-html="message.role === 'assistant' ? renderMarkdown(message.content) : escapeText(message.content)"></div>
                <span v-if="message.role === 'assistant' && message.loading && message.content" class="stream-cursor"></span>
                <div v-if="message.files?.length" class="message-files"><span v-for="file in message.files" :key="file.name"><el-icon><Document /></el-icon>{{ file.name }}</span></div>
                <div v-if="message.loading && !message.content" class="thinking"><span></span><span></span><span></span><em>{{ agentName(message.agent) }} 正在思考</em></div>
                <KnowledgeSourcesCard v-if="message.knowledgeSources" :payload="message.knowledgeSources" />
                <AgentInputFormCard v-if="message.inputForm" :form="message.inputForm" @submit="submitInputForm" />
                <el-button v-if="message.handoff?.page_url" class="handoff-action" type="primary" plain @click="router.push(message.handoff.page_url)">前往数据集页面完成人工标注 <el-icon><ArrowRight /></el-icon></el-button>
                <AgentConfirmationCard v-for="operation in (message.confirmations || [])" :key="operation.operation_uuid" :operation="operation" @changed="handleOperationCardChanged" />
              </div>
              <DetectionResultCard v-if="message.result" class="detection-result" :result="message.result" />
            </div>
          </article>
          <button
            v-if="showScrollToBottom"
            class="scroll-bottom-button"
            type="button"
            aria-label="回到底部"
            @click="scrollToBottomForce"
          >
            <el-icon><Bottom /></el-icon>
          </button>
        </div>

        <footer class="composer" @paste="handlePaste">
          <div v-if="selectedFiles.length" class="attachment-tray">
            <span v-for="(item, index) in selectedFiles" :key="item.id">
              <img v-if="item.preview" :src="item.preview" alt="" /><el-icon v-else><Document /></el-icon>
              <b>{{ item.file.name }}</b><button type="button" @click="removeFile(index)"><el-icon><Close /></el-icon></button>
            </span>
          </div>
          <div class="composer-box">
            <textarea v-model="inputText" rows="1" placeholder="输入消息" :disabled="agentStore.isLoading" @keydown.enter.exact.prevent="sendMessage"></textarea>
            <div class="composer-actions">
              <input ref="fileInputRef" type="file" multiple accept="image/jpeg,image/png,image/bmp,image/webp,.zip,video/mp4,video/quicktime,video/x-msvideo,.mkv" @change="selectFiles($event.target.files); $event.target.value = ''" />
              <el-tooltip content="添加图片、ZIP 或视频"><el-button text :icon="Paperclip" :disabled="agentStore.isLoading" @click="fileInputRef?.click()" /></el-tooltip>
              <span>{{ selectedFiles.length ? `${selectedFiles.length} 个附件` : 'Enter 发送 · Shift+Enter 换行' }}</span>
              <el-button v-if="agentStore.isLoading" class="send-button" type="danger" :icon="VideoPause" circle @click="stopStream" />
              <el-button v-else class="send-button" type="primary" :icon="Top" circle :disabled="!canSend" @click="sendMessage" />
            </div>
          </div>
        </footer>
      </main>

      <aside class="insight-panel" :aria-hidden="insightsCollapsed">
        <div class="insight-toolbar">
          <div class="insight-heading">
            <span>管理辅助</span>
            <small><i :class="{ online: agentStatus.configured }"></i>{{ agentStatus.configured ? '服务在线' : '未配置' }}</small>
          </div>
          <el-tooltip content="收起管理辅助" placement="left" :show-arrow="false">
            <el-button class="panel-toggle" :icon="DArrowRight" circle aria-label="收起管理辅助" @click="insightsCollapsed = true" />
          </el-tooltip>
        </div>
        <div class="insight-content">
        <section>
          <div class="panel-title"><span>Agent 团队</span><em>{{ activeAgents.length ? '正在协作' : '自动路由' }}</em></div>
          <div class="agent-list">
            <div v-for="agent in agents" :key="agent.name" :class="['agent-item', { active: activeAgents.includes(agent.name) }]">
              <span :class="agent.name"><el-icon><component :is="agent.icon" /></el-icon></span>
              <div><strong>{{ agent.label }}</strong><small>{{ agent.description }}</small></div>
              <i></i>
            </div>
          </div>
        </section>
        <section class="pending-section">
          <div class="panel-title"><span>待确认操作</span><em>{{ pendingOperations.length }}</em></div>
          <div v-if="pendingOperations.length" class="pending-list">
            <button v-for="operation in pendingOperations.slice(0, 5)" :key="operation.operation_uuid" type="button" @click="openOperationSession(operation)">
              <span :class="operation.risk_level?.toLowerCase()">{{ operation.risk_level }}</span>
              <div><strong>{{ operation.impact?.title || operation.action }}</strong><small>{{ operation.impact?.summary }}</small></div>
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
          <div v-else class="pending-empty"><el-icon><CircleCheckFilled /></el-icon><span>当前没有待确认操作</span></div>
        </section>
        <section class="safety-card">
          <el-icon><Clock /></el-icon>
          <div><strong>10 分钟确认窗口</strong><small>令牌过期或已使用后不能重复执行，所有结果都会进入审计日志。</small></div>
        </section>
        </div>
      </aside>

      <el-dialog v-model="operationDialogVisible" title="待确认操作" width="560px" append-to-body destroy-on-close>
        <AgentConfirmationCard v-if="focusedOperation" :operation="focusedOperation" @changed="handleOperationCardChanged" />
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, Bottom, ChatDotRound, CircleCheckFilled, Clock, Close, Connection, Cpu, DArrowLeft, DArrowRight, DataAnalysis,
  Delete, Document, Files, MagicStick, Operation, Paperclip, Plus, PriceTag,
  Refresh, Top, VideoPause, View,
} from '@element-plus/icons-vue'
import AgentConfirmationCard from '@/components/AgentConfirmationCard.vue'
import AgentInputFormCard from '@/components/AgentInputFormCard.vue'
import { handleAuthExpired } from '@/utils/authExpiry'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import KnowledgeSourcesCard from '@/components/KnowledgeSourcesCard.vue'
import {
  createChatSessionApi, deleteChatSessionApi, getAgentStatusApi,
  getChatSessionApi, getChatSessionsApi, uploadChatFilesApi,
} from '@/api/chat'
import { getAgentOperationApi, listAgentOperationsApi } from '@/api/agentOperations'
import { useAgentStore } from '@/stores/agent'
import { CHAT_ATTACHMENT_MAX_COUNT, chatAttachmentKey, prepareChatAttachmentAdditions } from '@/utils/chatAttachments'
import { renderMarkdown } from '@/utils/markdown'
import { streamChat } from '@/utils/stream'

const router = useRouter()
const agentStore = useAgentStore()
const inputText = computed({
  get: () => agentStore.draftText,
  set: (value) => { agentStore.draftText = value },
})
const selectedFiles = computed({
  get: () => agentStore.draftAttachments,
  set: (value) => { agentStore.draftAttachments = value },
})
const fileInputRef = ref(null)
const messageListRef = ref(null)
const sessionLoading = ref(false)
const sessionsCollapsed = ref(false)
const insightsCollapsed = ref(false)
const newChatViewKey = ref(0)
const agentStatus = ref({ configured: false, model: 'DeepSeek', agents: [] })
const pendingOperations = ref([])
const pendingFormSubmission = ref(null)
const canSend = computed(() => Boolean(inputText.value.trim() || selectedFiles.value.length))
const activeAgents = computed(() => {
  const last = [...agentStore.messages].reverse().find((message) => message.role === 'assistant' && message.agent)
  if (!last) return []
  // When multiple agents collaborate, highlight all of them in the team panel.
  if (Array.isArray(last.parallelAgents) && last.parallelAgents.length > 1) {
    return last.parallelAgents
  }
  return [last.agent.split(/\s*[+,]\s*/)[0]].filter(Boolean)
})

const agents = [
  { name: 'detection', label: 'Detection', description: '图片与视频商品检测', icon: View },
  { name: 'dataset', label: 'Dataset', description: '版本、样品与标注流程', icon: Files },
  { name: 'training', label: 'Training', description: '训练任务与模型发布', icon: DataAnalysis },
  { name: 'catalog', label: 'Catalog', description: '商品目录与价目表', icon: PriceTag },
  { name: 'knowledge', label: 'Knowledge', description: '知识库与故障案例', icon: MagicStick },
]
const quickPrompts = [
  { title: '查看数据集', description: '列出全部版本与当前状态', prompt: '查看所有数据集版本，并标出当前版本', icon: Files, tone: 'dataset' },
  { title: '训练进度', description: '检查最近任务和关键指标', prompt: '查看最近的训练任务进度和关键指标', icon: DataAnalysis, tone: 'training' },
  { title: '管理价目表', description: '检查未定价商品', prompt: '查看当前数据集里还没有定价的商品', icon: PriceTag, tone: 'catalog' },
  { title: '故障排查', description: '检索知识库和故障案例', prompt: '帮我检查最近常见的商品漏检原因和排查步骤', icon: MagicStick, tone: 'knowledge' },
]

// 上翻超过阈值时显示“回到底部”浮动按钮。
const showScrollToBottom = ref(false)
function handleMessageScroll() {
  const el = messageListRef.value
  if (!el) return
  showScrollToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight > 300
}
async function scrollToBottomForce() { await scrollBottom(); showScrollToBottom.value = false }

onMounted(async () => {
  messageListRef.value?.addEventListener('scroll', handleMessageScroll, { passive: true })
  try { agentStatus.value = await getAgentStatusApi() } catch { /* 全局请求层处理 */ }
  await Promise.all([loadSessions(), loadPendingOperations()])
  // 历史列表只用于展示。首次登录或刷新后的第一次进入保持空白新对话；
  // 仅恢复本次浏览器会话中已经明确选中的活动会话。
  if (agentStore.currentSessionId && !agentStore.messages.length) {
    const currentSession = agentStore.sessions.find(
      (session) => session.session_uuid === agentStore.currentSessionId,
    )
    if (currentSession) await openSession(currentSession.session_uuid)
  }
})

onBeforeUnmount(() => {
  messageListRef.value?.removeEventListener('scroll', handleMessageScroll)
})

function agentName(name) {
  const map = { detection: 'Detection', dataset: 'Dataset', training: 'Training', catalog: 'Catalog', knowledge: 'Knowledge' }
  const parts = String(name || '').split(/\s*[+,]\s*/).filter(Boolean)
  if (parts.length <= 1) return map[name] || 'VisionPay Agent'
  return parts.map((part) => map[part] || part).join(' + ') + ' Agent'
}
function toolName(name) { return ({
  list_dataset_versions: '读取全部数据集版本', get_current_dataset_version: '读取当前数据集',
  get_dataset_version_detail: '读取版本详情', prepare_add_samples_handoff: '创建人工标注交接',
  preview_derive_dataset_version: '预览派生版本', preview_freeze_dataset_version: '校验并预览冻结',
  preview_archive_dataset_version: '预览归档影响', preview_delete_product_samples: '统计商品删除影响',
  preview_delete_dataset_draft: '统计草稿删除影响', list_training_tasks: '读取训练任务',
  get_training_status: '读取训练进度', get_training_metrics: '读取训练指标',
  preview_start_training: '预览训练参数', preview_stop_training: '预览停止训练',
  preview_set_default_model: '比较新旧默认模型', list_product_prices: '读取实时价目表',
  preview_update_product_price: '预览价格变更', preview_clear_product_price: '预览清除价格',
  request_user_input_form: '生成参数问询表单', get_platform_agent_capabilities: '读取 Agent 能力边界',
  search_knowledge: '检索知识库', search_incidents: '检索故障案例',
  search_management_knowledge: '检索知识库', search_fault_cases: '检索故障案例',
  parallel_running: '协调多个 Agent 协作', pipeline_running: '按流水线依次执行', supervisor_summary: '汇总各 Agent 结果',
})[name] || name }
// 编排类状态不是业务工具，不显示“正在调用”前缀。
function toolPrefix(name) { return ['parallel_running', 'pipeline_running', 'supervisor_summary'].includes(name) ? '' : '正在调用' }
function escapeText(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML.replace(/\n/g, '<br>') }
function formatTime(value) { if (!value) return ''; const date = new Date(value); if (Number.isNaN(date.getTime())) return ''; return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
async function scrollBottom() { await nextTick(); if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight }
// 流式输出时，只有当用户本来就在底部附近才自动跟随滚动，避免打断用户查看上文。
async function scrollBottomIfNearBottom(threshold = 120) {
  await nextTick()
  const el = messageListRef.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distance <= threshold) el.scrollTop = el.scrollHeight
}

async function loadSessions() {
  sessionLoading.value = true
  try { agentStore.sessions = (await getChatSessionsApi()).items }
  finally { sessionLoading.value = false }
}
async function loadPendingOperations() {
  try { pendingOperations.value = (await listAgentOperationsApi({ status: 'pending' })).items || [] }
  catch { pendingOperations.value = [] }
}
async function ensureSession() {
  if (agentStore.currentSessionId) return agentStore.currentSessionId
  const session = await createChatSessionApi()
  agentStore.currentSessionId = session.session_uuid
  return session.session_uuid
}
function createNewChat() {
  stopStream(); agentStore.currentSessionId = null; agentStore.messages = []; inputText.value = ''; pendingFormSubmission.value = null; clearFiles(); newChatViewKey.value += 1
}
async function openSession(sessionUuid) {
  if (agentStore.isLoading || sessionUuid === agentStore.currentSessionId && agentStore.messages.length) return
  stopStream(); sessionLoading.value = true
  try {
    const data = await getChatSessionApi(sessionUuid)
    agentStore.currentSessionId = sessionUuid
    agentStore.messages = data.messages.map((message) => ({
      ...message,
      inputForm: message.input_form,
      knowledgeSources: message.knowledge_sources,
      // 历史消息统一成确认卡数组：新数据用 confirmations，旧数据用单个 confirmation 兜底。
      confirmations: message.confirmations || (message.confirmation ? [message.confirmation] : []),
      loading: false,
    }))
    await syncMessageConfirmations()
    await scrollBottom()
  } finally { sessionLoading.value = false }
}
// 同步对话页里所有确认卡的最新状态（弹窗确认、切换会话后都会用到）。
async function syncMessageConfirmations() {
  await Promise.allSettled(
    agentStore.messages
      .flatMap((message) => message.confirmations || [])
      .filter((operation) => operation?.operation_uuid)
      .map(async (operation) => {
        Object.assign(operation, await getAgentOperationApi(operation.operation_uuid))
      }),
  )
}
// 侧边栏待确认操作：直接弹出该操作的确认卡，而不是静默跳转会话。
const focusedOperation = ref(null)
const operationDialogVisible = ref(false)
function openOperationSession(operation) { focusedOperation.value = operation; operationDialogVisible.value = true }
function handleOperationCardChanged() { loadPendingOperations(); syncMessageConfirmations() }
async function removeSession(session) {
  try {
    await ElMessageBox.confirm(`确定删除“${session.title}”吗？`, '删除对话', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await deleteChatSessionApi(session.session_uuid)
    agentStore.sessions = agentStore.sessions.filter((item) => item.session_uuid !== session.session_uuid)
    if (agentStore.currentSessionId === session.session_uuid) createNewChat()
  } catch (error) { if (error !== 'cancel' && error !== 'close') throw error }
}

function selectFiles(files) {
  const result = prepareChatAttachmentAdditions(selectedFiles.value, files)
  selectedFiles.value.push(...result.additions.map((file) => ({
    id: chatAttachmentKey(file),
    file,
    preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
  })))

  if (result.unsupportedCount) ElMessage.warning('仅支持图片、ZIP、MP4、AVI、MOV 或 MKV 文件')
  if (result.overflowCount) ElMessage.warning(`每次最多上传 ${CHAT_ATTACHMENT_MAX_COUNT} 个附件，超出的文件未添加`)
  else if (result.duplicateCount && !result.additions.length) ElMessage.info('所选文件已经在附件列表中')
}
function handleDrop(event) { if (!agentStore.isLoading) selectFiles(event.dataTransfer.files) }
function handlePaste(event) { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); selectFiles(files) } }
function removeFile(index) { const [item] = selectedFiles.value.splice(index, 1); if (item?.preview) URL.revokeObjectURL(item.preview) }
function clearFiles() { selectedFiles.value.forEach((item) => item.preview && URL.revokeObjectURL(item.preview)); selectedFiles.value = [] }

async function submitInputForm({ form, values }) {
  const fieldMap = Object.fromEntries((form.fields || []).map((field) => [field.name, field]))
  const details = Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== '').map(([name, value]) => {
    const field = fieldMap[name] || { label: name }
    const selected = field.options?.find((option) => option.value === value)
    const display = selected?.label || (Array.isArray(value) ? value.join('、') : value)
    return `${field.label}：${display}`
  })
  inputText.value = `已填写“${form.title || '任务参数'}”：\n${details.map((item) => `- ${item}`).join('\n')}`
  pendingFormSubmission.value = form.form_id ? { form_id: form.form_id, values } : null
  await sendMessage()
}

async function sendMessage() {
  if (!canSend.value || agentStore.isLoading) return
  if (!localStorage.getItem('vp_agent_token')) {
    handleAuthExpired({ redirectPath: '/chat' })
    return
  }
  const files = selectedFiles.value.map((item) => item.file)
  const formSubmission = pendingFormSubmission.value
  const lastAgent = activeAgents.value[0] || ''
  const text = inputText.value.trim() || (lastAgent === 'dataset' ? '我已选择样品图片，请继续添加样品流程' : '识别附件中的商品并汇总数量')
  let sessionUuid
  try { sessionUuid = await ensureSession() } catch (error) { ElMessage.error(error.message || '无法创建对话'); return }
  agentStore.addMessage({ role: 'user', content: text, files: files.map((file) => ({ name: file.name })) })
  const assistant = agentStore.addMessage({ role: 'assistant', content: '', loading: true, tool: '', result: null, agent: '', parallelAgents: [], _lastTextAgent: '', knowledgeSources: null, confirmations: [] })
  inputText.value = ''; agentStore.setLoading(true); scrollBottom()
  try {
    const upload = files.length ? await uploadChatFilesApi(files) : { files: [] }
    const stream = streamChat('/api/chat/stream', {
      message: text,
      attachment_paths: upload.files.map((file) => file.path),
      attachment_names: files.map((file) => ({ name: file.name })),
      form_submission: formSubmission,
      session_uuid: sessionUuid,
    }, {
      onMessage(event) {
        if (event.type === 'routing') {
          const isMulti = event.is_parallel || event.execution_mode === 'pipeline'
          assistant.agent = isMulti ? event.agents.join('+') : event.agent
          if (isMulti) assistant.parallelAgents = event.agents
        }
        if (event.type === 'parallel_progress') {
          if (Array.isArray(event.agents)) assistant.parallelAgents = event.agents
          if (event.status === 'started' || event.status === 'pipeline_started') assistant.tool = 'parallel_running'
          if (event.status === 'pipeline_step') assistant.tool = 'pipeline_running'
          if (event.status === 'summarizing') assistant.tool = 'supervisor_summary'
          if (event.status === 'completed') assistant.tool = ''
        }
        if (event.type === 'text_chunk') {
          const chunkAgent = event.agent || ''
          // 汇总回复是统一声音，不再按 Agent 打标签；仅当个别 Agent 直接输出时才标注来源。
          if (
            assistant.parallelAgents.length > 1 && chunkAgent && chunkAgent !== 'supervisor'
            && assistant._lastTextAgent !== chunkAgent
          ) {
            assistant._lastTextAgent = chunkAgent
            assistant.content += `\n\n**${agentName(chunkAgent)}**：\n\n`
          }
          assistant.content += event.content
        }
        if (event.type === 'tool_call') assistant.tool = event.tool
        if (event.type === 'tool_result') assistant.tool = ''
        if (event.type === 'knowledge_sources') { assistant.knowledgeSources = event; assistant.tool = '' }
        if (event.type === 'input_form') { assistant.inputForm = event.form; assistant.tool = '' }
        if (event.type === 'handoff_required') { assistant.handoff = event; assistant.tool = '' }
        if (event.type === 'confirmation_required') { assistant.confirmations.push(event.operation); assistant.confirmation = event.operation; assistant.tool = ''; loadPendingOperations() }
        if (event.type === 'detection_result') { assistant.result = event.result; assistant.tool = '' }
        if (event.type === 'error') assistant.content += `\n\n${event.content}`
        scrollBottomIfNearBottom()
      },
      onDone() { assistant.loading = false; assistant.tool = ''; agentStore.setLoading(false); agentStore.abortController = null; clearFiles(); loadSessions(); loadPendingOperations(); scrollBottomIfNearBottom() },
      onError(error) { assistant.content = error.message; assistant.loading = false; assistant.tool = ''; agentStore.setLoading(false); agentStore.abortController = null; scrollBottomIfNearBottom() },
    })
    pendingFormSubmission.value = null
    agentStore.abortController = stream.stop
  } catch (error) {
    assistant.content = error?.response?.data?.detail || error.message || '请求失败'
    assistant.loading = false; agentStore.setLoading(false)
  }
}
function stopStream() { agentStore.abort(); const last = agentStore.messages.at(-1); if (last?.role === 'assistant') { last.loading = false; last.tool = ''; if (!last.content) last.content = '已停止本次响应。' } }
</script>

<style lang="scss" scoped>
.agent-chat-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px;
  color: $text-primary;
}

.chat-layout {
  --session-column: 260px;
  --insight-column: 280px;
  min-height: 0;
  flex: 1;
  display: flex;
  gap: 0;
  overflow: hidden;
}

.chat-layout.sessions-collapsed {
  .session-panel {
    width: 0;
    flex-basis: 0;
    margin-right: 0;
    padding-right: 0;
    padding-left: 0;
    border-width: 0;
    opacity: 0;
    visibility: hidden;
    transform: translateX(-18px);
    pointer-events: none;
    transition-delay: 0s, 0s, 0s, 0s, 0s, 0s, 0s, .28s;
  }
}

.chat-layout.insights-collapsed {
  .insight-panel {
    width: 0;
    flex-basis: 0;
    margin-left: 0;
    padding-right: 0;
    padding-left: 0;
    border-width: 0;
    opacity: 0;
    visibility: hidden;
    transform: translateX(18px);
    pointer-events: none;
    transition-delay: 0s, 0s, 0s, 0s, 0s, 0s, 0s, .28s;
  }
}

.session-panel,
.conversation-panel,
.insight-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: $surface-color;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
}

.session-panel,
.insight-panel {
  overflow: hidden;
  opacity: 1;
  visibility: visible;
  transform: translateX(0);
  transition:
    width .28s cubic-bezier(.2, .8, .2, 1),
    flex-basis .28s cubic-bezier(.2, .8, .2, 1),
    margin .28s cubic-bezier(.2, .8, .2, 1),
    padding .28s cubic-bezier(.2, .8, .2, 1),
    border-width .18s ease,
    transform .28s cubic-bezier(.2, .8, .2, 1),
    opacity .18s ease,
    visibility 0s linear;
}

.session-panel {
  width: var(--session-column);
  flex: 0 0 var(--session-column);
  margin-right: 16px;
  padding: 14px;
}

.conversation-panel {
  position: relative;
  min-width: 0;
  flex: 1 1 auto;
}

.insight-panel {
  width: var(--insight-column);
  flex: 0 0 var(--insight-column);
  margin-left: 16px;
  padding: 14px;
}

.sidebar-toolbar,
.insight-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.insight-toolbar {
  justify-content: space-between;
}

.new-chat {
  flex: 1;
  height: 36px;
  border-radius: 10px;
  font-weight: 500;
}

.panel-toggle {
  width: 32px;
  min-width: 32px;
  height: 32px;
  border-radius: 50%;
  color: $text-secondary;
  border-color: transparent;
  background: transparent;

  &:hover {
    color: $text-primary;
    background: var(--vp-sidebar-active-bg);
  }
}

.panel-title {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  margin-bottom: 8px;
  color: $text-secondary;
  font-size: 12px;
  font-weight: 600;

  span { font-weight: 600; }
  em {
    font-style: normal;
    color: $text-secondary;
  }

  .el-button {
    height: 24px;
    padding: 0 6px;
    color: $text-placeholder;
  }
}

.session-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  margin: 0 -6px;
  padding: 0 6px;
}

.session-item {
  width: 100%;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 22px;
  align-items: center;
  gap: 8px;
  padding: 9px 8px;
  margin-bottom: 2px;
  border: none;
  border-radius: 10px;
  color: $text-primary;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background .15s ease;

  &:hover,
  &.active {
    background: var(--vp-sidebar-active-bg);
  }

  &.active { font-weight: 600; }
}

.session-icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: $text-secondary;
  background: transparent;
  font-size: 16px;
}

.session-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;

  strong {
    display: block;
    overflow: hidden;
    font-size: 13px;
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    color: $text-placeholder;
    font-size: 11px;
  }
}

.delete-session {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: $text-placeholder;
  opacity: 0;
  transition: opacity .15s ease, color .15s ease, background .15s ease;

  .session-item:hover & { opacity: 1; }
  &:hover {
    color: $danger-color;
    background: var(--vp-danger-bg);
  }
}

.session-empty {
  padding: 24px 0;
  color: $text-placeholder;
  font-size: 13px;
  text-align: center;
}

/* 右侧管理辅助 */
.insight-heading {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;

  span {
    color: $text-secondary;
    font-size: 12px;
    font-weight: 600;
  }

  small {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: $text-placeholder;
    font-size: 11px;
  }

  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: $danger-color;

    &.online { background: $success-color; }
  }
}

.insight-content {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
}

.insight-content section + section {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid $border-color;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 7px;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 10px;
  cursor: default;
  transition: background .15s ease;

  &.active { background: var(--vp-sidebar-active-bg); }

  > span {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    color: #fff;
    background: $primary-color;
    font-size: 16px;

    &.dataset { background: #8b5cf6; }
    &.training { background: #0ea5e9; }
    &.catalog { background: #f59e0b; }
    &.knowledge { background: #10b981; }
  }

  div {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  strong { font-size: 13px; font-weight: 600; }
  small {
    overflow: hidden;
    color: $text-placeholder;
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  > i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: $border-strong;
  }

  &.active > i { background: $success-color; }
}

.pending-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pending-list button {
  width: 100%;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid $border-color;
  border-radius: 10px;
  color: $text-primary;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease;

  &:hover {
    background: var(--vp-sidebar-active-bg);
    border-color: $border-strong;
  }

  > span {
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    color: #fff;
    background: $warning-color;
    font-size: 10px;
    font-weight: 700;

    &.r3 { background: $danger-color; }
  }

  div {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  strong {
    overflow: hidden;
    font-size: 12px;
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  small {
    overflow: hidden;
    color: $text-placeholder;
    font-size: 10px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.pending-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  color: $success-color;
  background: var(--vp-success-bg);
  font-size: 12px;
  font-weight: 500;

  .el-icon { font-size: 14px; }
}

.safety-card {
  display: flex;
  gap: 10px;
  padding: 12px;
  border: 1px solid $border-color;
  border-radius: 10px;
  color: $text-primary;
  background: transparent;

  .el-icon {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    color: $primary-color;
    background: $primary-soft;
    font-size: 15px;
  }

  div {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  strong { font-size: 13px; font-weight: 600; }
  small { color: $text-placeholder; font-size: 11px; line-height: 1.45; }
}

/* 对话区 */
.conversation-panel.has-floating-controls .message-list { padding-top: 72px; }

.floating-panel-controls {
  position: absolute;
  inset: 0;
  z-index: 8;
  pointer-events: none;
}

.floating-control-capsule {
  position: absolute;
  top: 14px;
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid $border-color;
  border-radius: 999px;
  color: $text-secondary;
  background: rgba($surface-color, .92);
  box-shadow: $shadow-md;
  pointer-events: auto;
  animation: panel-control-in .22s .1s both;
}

.floating-control-capsule--left { left: 14px; }
.floating-control-capsule--right { right: 14px; }

.floating-control-button {
  width: 30px;
  min-width: 30px;
  height: 30px;
  margin: 0;
  border-radius: 50%;
  color: inherit;
  border-color: transparent;
  background: transparent;

  &:hover {
    color: $primary-color;
    background: $primary-soft;
  }
}

.floating-control-divider {
  width: 1px;
  height: 16px;
  background: $border-color;
}

.message-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 20px 20px 12px;
  scroll-behavior: smooth;
  transition: padding-top .22s cubic-bezier(.2, .8, .2, 1);
}

// sticky 吸附在消息滚动区可视底部，不遮挡输入框；纯箭头圆形按钮。
.scroll-bottom-button {
  position: sticky;
  bottom: 12px;
  z-index: 30;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  margin: -48px 8px 0 auto;
  border: 1px solid $border-color;
  border-radius: 50%;
  color: $text-secondary;
  background: $surface-color;
  box-shadow: $shadow-md;
  font-size: 16px;
  cursor: pointer;
  transition: color .2s ease, border-color .2s ease, background-color .2s ease;

  &:hover {
    color: $primary-color;
    border-color: $primary-color;
    background: $primary-soft;
  }
}

.welcome-state {
  max-width: 720px;
  margin: 0 auto;
  padding: 48px 0;
  text-align: center;
  animation: new-conversation-in .34s cubic-bezier(.2, .8, .2, 1) both;
}

.welcome-mark {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  margin: 0 auto;
  border-radius: 16px;
  color: #fff;
  background: linear-gradient(145deg, $primary-color, color-mix(in srgb, $primary-color 60%, #7c3aed));
  font-size: 24px;
}

.welcome-state > span {
  display: block;
  margin-top: 16px;
  color: $text-secondary;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.welcome-state h2 {
  margin: 8px 0;
  font-size: 26px;
  font-weight: 700;
}

.welcome-state > p {
  max-width: 480px;
  margin: 0 auto;
  color: $text-secondary;
  font-size: 13px;
  line-height: 1.6;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-top: 28px;
}

.quick-grid button {
  position: relative;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 16px;
  grid-template-rows: auto auto;
  gap: 2px 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid $border-color;
  border-radius: 10px;
  color: $text-primary;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: border-color .15s ease, background .15s ease;

  &:hover {
    border-color: $border-strong;
    background: var(--vp-sidebar-active-bg);
  }

  > span {
    grid-row: 1 / 3;
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    color: #fff;
    background: $primary-color;
    font-size: 16px;

    &.dataset { background: #8b5cf6; }
    &.training { background: #0ea5e9; }
    &.catalog { background: #f59e0b; }
    &.knowledge { background: #10b981; }
  }

  strong { font-size: 13px; font-weight: 600; }
  small { color: $text-placeholder; font-size: 11px; }

  .quick-arrow {
    grid-row: 1;
    grid-column: 3;
    color: $text-placeholder;
    font-size: 12px;
  }
}

.message-row {
  display: flex;
  margin-bottom: 20px;
}

.message-row.user { justify-content: flex-end; }

.message-column {
  min-width: 0;
  max-width: min(760px, 100%);
}

.message-row.user .message-column {
  max-width: min(680px, 85%);
}

.agent-activity {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: $text-secondary;
  font-size: 11px;
}

.agent-activity > i {
  width: 12px;
  height: 1px;
  background: $border-strong;
}

.agent-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 6px;
  color: $success-color;
  background: var(--vp-success-bg);
  font-size: 11px;
  font-weight: 600;

  .el-icon { font-size: 12px; }
}

.tool-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 6px;
  color: $warning-color;
  background: var(--vp-warning-bg);
  font-size: 11px;
  font-weight: 600;

  small { font-weight: 500; opacity: .85; }
}

.activity-status {
  color: $text-placeholder;
  font-size: 11px;
}

.message-bubble {
  padding: 12px 14px;
  border: 1px solid $border-color;
  border-radius: 12px;
  color: $text-primary;
  background: $surface-color;
}

.message-row.user .message-bubble {
  border-color: transparent;
  border-radius: 12px 12px 4px 12px;
  background: var(--vp-sidebar-active-bg);
}

.message-content {
  font-size: 14px;
  line-height: 1.72;
  overflow-wrap: anywhere;

  :deep(p) { margin: 0 0 10px; }
  :deep(p:last-child) { margin-bottom: 0; }
  :deep(h1), :deep(h2), :deep(h3), :deep(h4) { margin: 14px 0 8px; color: $text-primary; }
  :deep(ul), :deep(ol) { padding-left: 1.4em; margin: 8px 0; }
  :deep(li) { margin: 4px 0; }
  :deep(code) {
    padding: 2px 5px;
    border-radius: 5px;
    background: var(--vp-sidebar-active-bg);
    font-size: 12px;
  }
  :deep(pre) {
    padding: 10px;
    border-radius: 8px;
    background: var(--vp-sidebar-active-bg);
    overflow-x: auto;
  }
  :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 13px;
  }
  :deep(th), :deep(td) {
    padding: 6px 10px;
    border: 1px solid $border-color;
    text-align: left;
  }
  :deep(th) { background: var(--vp-sidebar-active-bg); }
}

.message-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 8px;
    border-radius: 6px;
    color: $text-secondary;
    background: var(--vp-sidebar-active-bg);
    font-size: 11px;
  }
}

.thinking {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;

  span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: $text-placeholder;
    animation: thinking 1.2s infinite ease-in-out;

    &:nth-child(2) { animation-delay: .15s; }
    &:nth-child(3) { animation-delay: .3s; }
  }

  em {
    color: $text-placeholder;
    font-size: 12px;
  }
}

.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  background: $primary-color;
  vertical-align: middle;
  animation: blink 1s step-end infinite;
}

.handoff-action {
  margin-top: 10px;
  height: 34px;
  border-radius: 8px;
}

.detection-result {
  margin-top: 12px;
}

/* Composer */
.composer {
  flex-shrink: 0;
  padding: 12px 16px 16px;
  border-top: 1px solid $border-color;
  background: $surface-color;
  border-radius: 0 0 $border-radius-md $border-radius-md;
}

.attachment-tray {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 8px;

  > span {
    flex-shrink: 0;
    min-width: 130px;
    max-width: 220px;
    height: 34px;
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr) 22px;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border: 1px solid $border-color;
    border-radius: 8px;
    background: var(--vp-sidebar-active-bg);

    img {
      width: 28px;
      height: 28px;
      object-fit: cover;
      border-radius: 5px;
    }

    b {
      overflow: hidden;
      font-size: 11px;
      font-weight: 500;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    button {
      width: 20px;
      height: 20px;
      display: grid;
      place-items: center;
      border: 0;
      border-radius: 5px;
      color: $text-placeholder;
      background: transparent;
      cursor: pointer;

      &:hover { color: $danger-color; background: var(--vp-danger-bg); }
    }
  }
}

.composer-box {
  padding: 10px 12px;
  border: 1px solid $border-color;
  border-radius: 14px;
  background: $surface-color;
  transition: border-color .2s ease, box-shadow .2s ease;

  &:focus-within {
    border-color: $primary-color;
    box-shadow: $ring-primary;
  }
}

.composer textarea {
  width: 100%;
  min-height: 38px;
  max-height: 120px;
  padding: 4px 2px;
  resize: none;
  border: 0;
  outline: 0;
  color: $text-primary;
  background: transparent;
  font: inherit;
  font-size: 14px;
  line-height: 1.5;

  &::placeholder { color: $text-placeholder; }
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;

  input { display: none; }

  > span {
    flex: 1;
    color: $text-placeholder;
    font-size: 11px;
  }

  .el-button {
    width: 32px;
    height: 32px;
    min-height: 32px;
    padding: 0;
    border-radius: 8px;
  }
}

.send-button {
  width: 34px !important;
  height: 34px !important;
  border-radius: 10px !important;
}

/* 动画 */
@keyframes panel-control-in {
  from { opacity: 0; transform: translateY(-6px) scale(.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes new-conversation-in {
  from { opacity: 0; transform: translateY(14px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes thinking {
  0%, 70%, 100% { opacity: .25; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-2px); }
}

@keyframes blink {
  0%, 45% { opacity: 1; }
  46%, 100% { opacity: 0; }
}

/* 暗色 */
:global(html.dark .agent-chat-page) { color: var(--vp-text); }
:global(html.dark .agent-chat-page .session-panel),
:global(html.dark .agent-chat-page .conversation-panel),
:global(html.dark .agent-chat-page .insight-panel),
:global(html.dark .agent-chat-page .message-bubble),
:global(html.dark .agent-chat-page .composer) {
  background: var(--vp-surface);
  border-color: var(--vp-border);
}
:global(html.dark .agent-chat-page .message-row.user .message-bubble) {
  background: var(--vp-sidebar-active-bg);
  border-color: transparent;
}
:global(html.dark .agent-chat-page .session-item:hover),
:global(html.dark .agent-chat-page .session-item.active),
:global(html.dark .agent-chat-page .agent-item.active),
:global(html.dark .agent-chat-page .quick-grid button:hover),
:global(html.dark .agent-chat-page .pending-list button:hover),
:global(html.dark .agent-chat-page) .message-content :deep(code),
:global(html.dark .agent-chat-page) .message-content :deep(pre),
:global(html.dark .agent-chat-page .message-files span),
:global(html.dark .agent-chat-page .attachment-tray > span) { background: var(--vp-sidebar-active-bg); }
:global(html.dark .agent-chat-page .composer-box:focus-within) { border-color: var(--vp-primary); box-shadow: var(--vp-ring); }
:global(html.dark .agent-chat-page .welcome-mark) { color: #fff; }
:global(html.dark .agent-chat-page .floating-control-capsule) {
  background: rgba(23, 26, 33, .95);
  border-color: var(--vp-border);
}

@media (max-width: 1180px) {
  .chat-layout { --session-column: 220px; --insight-column: 250px; }
}

@media (max-width: 920px) {
  .chat-layout { display: grid; grid-template-columns: 1fr; overflow: visible; }
  .session-panel,
  .conversation-panel,
  .insight-panel {
    grid-column: auto;
    position: static;
    width: auto;
    flex-basis: auto;
    margin: 0;
    border: 1px solid $border-color;
  }
  .chat-layout.sessions-collapsed .session-panel,
  .chat-layout.insights-collapsed .insight-panel { display: none; }
  .conversation-panel { min-height: 560px; }
  .message-list, .composer { padding-left: 14px; padding-right: 14px; }
  .welcome-state { padding: 32px 0; }
}

@media (max-width: 640px) {
  .agent-chat-page { padding: 12px; }
  .quick-grid { grid-template-columns: 1fr; }
  .message-column { max-width: 100%; }
  .message-row.user .message-column { max-width: 92%; }
}

@media (prefers-reduced-motion: reduce) {
  .session-panel,
  .insight-panel,
  .message-list { transition: none; }

  .floating-control-capsule,
  .welcome-state { animation: none; }
}
</style>
