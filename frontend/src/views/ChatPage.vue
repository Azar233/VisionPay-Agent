<template>
  <div class="agent-chat-page" @dragover.prevent @drop.prevent="handleDrop">
    <header class="page-header">
      <div>
        <span class="eyebrow"><i></i> VisionPay Intelligence</span>
        <h1>管理智能体</h1>
        <p>用自然语言管理数据集、训练、价目表，也可以上传素材进行商品检测。</p>
      </div>
      <div class="header-state">
        <span :class="['status-dot', { online: agentStatus.configured }]"></span>
        <div><strong>{{ agentStatus.configured ? 'Agent 服务在线' : 'Agent 未配置' }}</strong><small>{{ agentStatus.model || 'DeepSeek' }} · {{ agentStatus.agents?.length || 5 }} 个领域</small></div>
      </div>
    </header>

    <div :class="['chat-layout', { 'sessions-collapsed': sessionsCollapsed, 'insights-collapsed': insightsCollapsed }]">
      <aside :class="['session-panel', { collapsed: sessionsCollapsed }]">
        <div class="sidebar-toolbar">
          <el-tooltip content="新建对话" placement="right" :show-arrow="false" :disabled="!sessionsCollapsed">
            <el-button class="new-chat" type="primary" :icon="Plus" :circle="sessionsCollapsed" @click="createNewChat">
              <span v-show="!sessionsCollapsed">新建对话</span>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="sessionsCollapsed ? '展开历史对话' : '收起历史对话'" placement="right" :show-arrow="false">
            <el-button class="panel-toggle" :icon="sessionsCollapsed ? DArrowRight : DArrowLeft" circle @click="sessionsCollapsed = !sessionsCollapsed" />
          </el-tooltip>
        </div>
        <div v-show="!sessionsCollapsed" class="panel-title"><span>最近对话</span><el-button text :icon="Refresh" :loading="sessionLoading" @click="loadSessions" /></div>
        <div v-show="!sessionsCollapsed" class="session-list" v-loading="sessionLoading">
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
        <div v-show="!sessionsCollapsed" class="privacy-note"><el-icon><CircleCheckFilled /></el-icon><span>写操作必须经过影响预览与一次性确认</span></div>
      </aside>

      <main class="conversation-panel">
        <div ref="messageListRef" class="message-list">
          <section v-if="!agentStore.messages.length" class="welcome-state">
            <div class="welcome-orb"><el-icon><MagicStick /></el-icon></div>
            <span>Multi-Agent Workspace</span>
            <h2>今天想管理什么？</h2>
            <p>我会自动选择合适的领域 Agent。涉及写入、删除或模型切换时，会先展示完整影响范围。</p>
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
                  <span class="tool-state"><el-icon><Operation /></el-icon><small>正在调用</small>{{ toolName(message.tool) }}</span>
                </template>
                <span v-else-if="message.loading" class="activity-status">正在处理</span>
              </div>
              <div class="message-bubble">
                <div v-if="message.content" class="message-content" v-html="message.role === 'assistant' ? renderMarkdown(message.content) : escapeText(message.content)"></div>
                <span v-if="message.role === 'assistant' && message.loading && message.content" class="stream-cursor"></span>
                <div v-if="message.files?.length" class="message-files"><span v-for="file in message.files" :key="file.name"><el-icon><Document /></el-icon>{{ file.name }}</span></div>
                <div v-if="message.loading && !message.content" class="thinking"><span></span><span></span><span></span><em>{{ agentName(message.agent) }} 正在思考</em></div>
                <AgentInputFormCard v-if="message.inputForm" :form="message.inputForm" @submit="submitInputForm" />
                <el-button v-if="message.handoff?.page_url" class="handoff-action" type="primary" plain @click="router.push(message.handoff.page_url)">前往数据集页面完成人工标注 <el-icon><ArrowRight /></el-icon></el-button>
                <AgentConfirmationCard v-if="message.confirmation" :operation="message.confirmation" @changed="loadPendingOperations" />
              </div>
              <DetectionResultCard v-if="message.result" class="detection-result" :result="message.result" />
            </div>
          </article>
        </div>

        <footer class="composer" @paste="handlePaste">
          <div v-if="selectedFiles.length" class="attachment-tray">
            <span v-for="(item, index) in selectedFiles" :key="item.id">
              <img v-if="item.preview" :src="item.preview" alt="" /><el-icon v-else><Document /></el-icon>
              <b>{{ item.file.name }}</b><button type="button" @click="removeFile(index)"><el-icon><Close /></el-icon></button>
            </span>
          </div>
          <div class="composer-box">
            <textarea v-model="inputText" rows="1" placeholder="向管理智能体发消息…" :disabled="agentStore.isLoading" @keydown.enter.exact.prevent="sendMessage"></textarea>
            <div class="composer-actions">
              <input ref="fileInputRef" type="file" multiple accept="image/jpeg,image/png,image/bmp,image/webp,.zip,video/mp4,video/quicktime,video/x-msvideo,.mkv" @change="selectFiles($event.target.files); $event.target.value = ''" />
              <el-tooltip content="添加图片、ZIP 或视频"><el-button text :icon="Paperclip" :disabled="agentStore.isLoading" @click="fileInputRef?.click()" /></el-tooltip>
              <span>{{ selectedFiles.length ? `${selectedFiles.length} 个附件` : 'Enter 发送 · Shift+Enter 换行' }}</span>
              <el-button v-if="agentStore.isLoading" class="send-button" type="danger" :icon="VideoPause" circle @click="stopStream" />
              <el-button v-else class="send-button" type="primary" :icon="Promotion" circle :disabled="!canSend" @click="sendMessage" />
            </div>
          </div>
        </footer>
      </main>

      <aside :class="['insight-panel', { collapsed: insightsCollapsed }]">
        <div class="insight-toolbar">
          <span v-show="!insightsCollapsed">管理辅助</span>
          <el-tooltip :content="insightsCollapsed ? '展开管理辅助' : '收起管理辅助'" placement="left" :show-arrow="false">
            <el-button class="panel-toggle" :icon="insightsCollapsed ? DArrowLeft : DArrowRight" circle @click="insightsCollapsed = !insightsCollapsed" />
          </el-tooltip>
        </div>
        <div v-show="!insightsCollapsed" class="insight-content">
        <section>
          <div class="panel-title"><span>Agent 团队</span><em>{{ activeAgent ? '正在协作' : '自动路由' }}</em></div>
          <div class="agent-list">
            <div v-for="agent in agents" :key="agent.name" :class="['agent-item', { active: activeAgent === agent.name }]">
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
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, ChatDotRound, CircleCheckFilled, Clock, Close, Cpu, DArrowLeft, DArrowRight, DataAnalysis,
  Delete, Document, Files, MagicStick, Operation, Paperclip, Plus, PriceTag,
  Promotion, Refresh, VideoPause, View,
} from '@element-plus/icons-vue'
import AgentConfirmationCard from '@/components/AgentConfirmationCard.vue'
import AgentInputFormCard from '@/components/AgentInputFormCard.vue'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
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
const inputText = ref('')
const selectedFiles = ref([])
const fileInputRef = ref(null)
const messageListRef = ref(null)
const sessionLoading = ref(false)
const sessionsCollapsed = ref(false)
const insightsCollapsed = ref(false)
const agentStatus = ref({ configured: false, model: 'DeepSeek', agents: [] })
const pendingOperations = ref([])
const pendingFormSubmission = ref(null)
const canSend = computed(() => Boolean(inputText.value.trim() || selectedFiles.value.length))
const activeAgent = computed(() => [...agentStore.messages].reverse().find((message) => message.role === 'assistant' && message.agent)?.agent || '')

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

onMounted(async () => {
  try { agentStatus.value = await getAgentStatusApi() } catch { /* 全局请求层处理 */ }
  await Promise.all([loadSessions(), loadPendingOperations()])
  if (!agentStore.messages.length && agentStore.sessions.length) {
    const currentSession = agentStore.sessions.find(
      (session) => session.session_uuid === agentStore.currentSessionId,
    )
    await openSession((currentSession || agentStore.sessions[0]).session_uuid)
  }
})
// The SSE stream belongs to the global agent store, so route changes only
// release page-local file previews. Users can still stop it explicitly.
onBeforeUnmount(clearFiles)

function agentName(name) { return ({ detection: 'Detection Agent', dataset: 'Dataset Agent', training: 'Training Agent', catalog: 'Catalog Agent', knowledge: 'Knowledge Agent' })[name] || 'VisionPay Agent' }
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
})[name] || name }
function escapeText(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML.replace(/\n/g, '<br>') }
function formatTime(value) { if (!value) return ''; const date = new Date(value); if (Number.isNaN(date.getTime())) return ''; return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
async function scrollBottom() { await nextTick(); if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight }

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
  stopStream(); agentStore.currentSessionId = null; agentStore.messages = []; inputText.value = ''; pendingFormSubmission.value = null; clearFiles()
}
async function openSession(sessionUuid) {
  if (agentStore.isLoading || sessionUuid === agentStore.currentSessionId && agentStore.messages.length) return
  stopStream(); sessionLoading.value = true
  try {
    const data = await getChatSessionApi(sessionUuid)
    agentStore.currentSessionId = sessionUuid
    agentStore.messages = data.messages.map((message) => ({ ...message, inputForm: message.input_form, loading: false }))
    await Promise.allSettled(agentStore.messages.filter((message) => message.confirmation?.operation_uuid).map(async (message) => {
      Object.assign(message.confirmation, await getAgentOperationApi(message.confirmation.operation_uuid))
    }))
    await scrollBottom()
  } finally { sessionLoading.value = false }
}
async function openOperationSession(operation) { await openSession(operation.session_uuid); await scrollBottom() }
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
    ElMessage.error('登录已过期，请重新登录')
    router.push({ path: '/login', query: { redirect: '/chat' } })
    return
  }
  const files = selectedFiles.value.map((item) => item.file)
  const formSubmission = pendingFormSubmission.value
  const lastAgent = activeAgent.value
  const text = inputText.value.trim() || (lastAgent === 'dataset' ? '我已选择样品图片，请继续添加样品流程' : '识别附件中的商品并汇总数量')
  let sessionUuid
  try { sessionUuid = await ensureSession() } catch (error) { ElMessage.error(error.message || '无法创建对话'); return }
  agentStore.addMessage({ role: 'user', content: text, files: files.map((file) => ({ name: file.name })) })
  const assistant = agentStore.addMessage({ role: 'assistant', content: '', loading: true, tool: '', result: null, agent: '' })
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
        if (event.type === 'routing') assistant.agent = event.agent
        if (event.type === 'text_chunk') assistant.content += event.content
        if (event.type === 'tool_call') assistant.tool = event.tool
        if (event.type === 'tool_result') assistant.tool = ''
        if (event.type === 'input_form') { assistant.inputForm = event.form; assistant.tool = '' }
        if (event.type === 'handoff_required') { assistant.handoff = event; assistant.tool = '' }
        if (event.type === 'confirmation_required') { assistant.confirmation = event.operation; assistant.tool = ''; loadPendingOperations() }
        if (event.type === 'detection_result') { assistant.result = event.result; assistant.tool = '' }
        if (event.type === 'error') assistant.content += `\n\n${event.content}`
        scrollBottom()
      },
      onDone() { assistant.loading = false; assistant.tool = ''; agentStore.setLoading(false); agentStore.abortController = null; clearFiles(); loadSessions(); loadPendingOperations(); scrollBottom() },
      onError(error) { assistant.content = error.message; assistant.loading = false; assistant.tool = ''; agentStore.setLoading(false); agentStore.abortController = null; scrollBottom() },
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
.agent-chat-page { height: 100%; min-height: 680px; display: flex; flex-direction: column; gap: 14px; color: $text-primary; }
.page-header { min-height: 88px; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 16px 22px; border: 1px solid rgba(255,255,255,.82); border-radius: 22px; background: rgba(255,255,255,.78); box-shadow: 0 12px 40px rgba(15,23,42,.06); backdrop-filter: blur(18px); }.page-header h1 { margin: 4px 0 0; font-family: 'Space Grotesk','DM Sans',sans-serif; font-size: 26px; letter-spacing: -.03em; }.page-header p { margin: 4px 0 0; color: $text-secondary; font-size: 12px; }.eyebrow { display: flex; align-items: center; gap: 7px; color: $primary-color; font-size: 10px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }.eyebrow i { width: 7px; height: 7px; border-radius: 50%; background: $primary-color; box-shadow: 0 0 0 5px rgba(0,113,227,.1); }.header-state { display: flex; align-items: center; gap: 10px; padding: 9px 13px; border: 1px solid $border-color; border-radius: 14px; background: rgba(255,255,255,.8); }.header-state div { display: flex; flex-direction: column; }.header-state strong { font-size: 11px; }.header-state small { margin-top: 2px; color: $text-placeholder; font-size: 9px; }.status-dot { width: 9px; height: 9px; border-radius: 50%; background: $danger-color; }.status-dot.online { background: $success-color; box-shadow: 0 0 0 5px rgba(16,185,129,.12); }
.chat-layout { --session-column: 256px; --insight-column: 296px; min-height: 0; flex: 1; display: grid; grid-template-columns: var(--session-column) minmax(420px,1fr) var(--insight-column); overflow: hidden; border: 1px solid rgba(255,255,255,.9); border-radius: 24px; background: rgba(255,255,255,.82); box-shadow: 0 22px 60px rgba(15,23,42,.08); backdrop-filter: blur(20px); transition: grid-template-columns .28s cubic-bezier(.2,.75,.25,1); }.chat-layout.sessions-collapsed { --session-column: 72px; }.chat-layout.insights-collapsed { --insight-column: 72px; }.session-panel,.insight-panel { min-height: 0; padding: 16px; background: rgba(248,250,252,.78); transition: padding .28s ease; }.session-panel { display: flex; flex-direction: column; border-right: 1px solid $border-color; }.insight-panel { overflow-y: auto; border-left: 1px solid $border-color; }.session-panel.collapsed,.insight-panel.collapsed { padding: 12px; overflow: hidden; }.sidebar-toolbar,.insight-toolbar { display: flex; align-items: center; gap: 8px; }.sidebar-toolbar { min-height: 42px; }.insight-toolbar { min-height: 42px; justify-content: space-between; color: $text-secondary; font-size: 10px; font-weight: 900; letter-spacing: .05em; }.session-panel.collapsed .sidebar-toolbar,.insight-panel.collapsed .insight-toolbar { justify-content: center; flex-direction: column; gap: 8px; }.session-panel.collapsed .new-chat { width: 42px; padding: 0; }.new-chat { flex: 1; height: 42px; border-radius: 13px; box-shadow: 0 8px 20px rgba(0,113,227,.16); }.panel-toggle { width: 38px; min-width: 38px; height: 38px; color: $text-secondary; border-color: $border-color; background: rgba(255,255,255,.7); transition: .2s ease; }.panel-toggle:hover { color: $primary-color; border-color: rgba(0,113,227,.35); background: $primary-soft; }.panel-title { min-height: 38px; display: flex; align-items: center; justify-content: space-between; margin-top: 10px; color: $text-secondary; font-size: 10px; font-weight: 900; letter-spacing: .04em; }.panel-title em { padding: 3px 7px; border-radius: 10px; color: $primary-color; background: $primary-soft; font-size: 8px; font-style: normal; }.session-list { min-height: 90px; flex: 1; overflow-y: auto; }.session-item { width: 100%; display: grid; grid-template-columns: 30px minmax(0,1fr) 24px; align-items: center; gap: 8px; margin-bottom: 5px; padding: 8px; border: 0; border-radius: 12px; color: $text-secondary; background: transparent; text-align: left; cursor: pointer; transition: .2s ease; }.session-item:hover { background: #fff; transform: translateX(2px); }.session-item.active { color: $primary-color; background: #fff; box-shadow: 0 7px 18px rgba(15,23,42,.06); }.session-icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; background: $surface-muted; }.session-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.session-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }.session-copy small { color: $text-placeholder; font-size: 8px; }.delete-session { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 7px; opacity: 0; cursor: pointer; }.session-item:hover .delete-session { opacity: 1; }.delete-session:hover { color: $danger-color; background: rgba(239,68,68,.08); }.session-empty { padding: 30px 0; color: $text-placeholder; text-align: center; font-size: 10px; }.privacy-note { display: flex; gap: 7px; padding: 10px; border-radius: 11px; color: $text-secondary; background: rgba(16,185,129,.07); font-size: 9px; line-height: 1.5; }.privacy-note .el-icon { flex: 0 0 auto; margin-top: 2px; color: $success-color; }
.conversation-panel { min-width: 0; min-height: 0; display: flex; flex-direction: column; background: rgba(255,255,255,.72); }.message-list { min-height: 0; flex: 1; overflow-y: auto; padding: 28px max(24px,calc((100% - 820px)/2)); scroll-behavior: smooth; }.welcome-state { min-height: 100%; display: grid; align-content: center; justify-items: center; text-align: center; }.welcome-orb { width: 62px; height: 62px; display: grid; place-items: center; border-radius: 20px; color: #fff; background: linear-gradient(145deg,#0071e3,#7c3aed); box-shadow: 0 18px 40px rgba(79,70,229,.24); font-size: 26px; transform: rotate(-4deg); }.welcome-state > span { margin-top: 18px; color: $primary-color; font-size: 9px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }.welcome-state h2 { margin: 7px 0; font-family: 'Space Grotesk','DM Sans',sans-serif; font-size: 25px; letter-spacing: -.03em; }.welcome-state > p { max-width: 560px; margin: 0; color: $text-secondary; font-size: 12px; line-height: 1.7; }.quick-grid { width: min(100%,650px); display: grid; grid-template-columns: repeat(2,1fr); gap: 9px; margin-top: 24px; }.quick-grid button { position: relative; display: grid; grid-template-columns: 34px minmax(0,1fr) 18px; grid-template-rows: auto auto; gap: 2px 9px; align-items: center; padding: 12px; border: 1px solid $border-color; border-radius: 14px; color: $text-primary; background: rgba(255,255,255,.8); text-align: left; cursor: pointer; transition: .2s ease; }.quick-grid button:hover { border-color: rgba(0,113,227,.35); box-shadow: 0 10px 24px rgba(15,23,42,.08); transform: translateY(-2px); }.quick-grid button > span { grid-row: 1/3; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; color: #fff; background: $primary-color; }.quick-grid span.dataset { background: #8b5cf6; }.quick-grid span.training { background: #0ea5e9; }.quick-grid span.catalog { background: #f59e0b; }.quick-grid span.knowledge { background: #10b981; }.quick-grid strong { font-size: 11px; }.quick-grid small { color: $text-placeholder; font-size: 9px; }.quick-arrow { grid-column: 3; grid-row: 1/3; color: $text-placeholder; }
.message-row { display: grid; grid-template-columns: 34px minmax(0,1fr); gap: 11px; margin-bottom: 24px; }.avatar { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 11px; color: #fff; background: $primary-color; box-shadow: 0 7px 16px rgba(0,113,227,.18); }.avatar.user { color: $text-secondary; background: $surface-muted; box-shadow: none; }.avatar.dataset { background: #8b5cf6; }.avatar.training { background: #0ea5e9; }.avatar.catalog { background: #f59e0b; }.avatar.knowledge { background: #10b981; }.message-column { min-width: 0; max-width: min(100%,820px); }.message-row.user .message-column { justify-self: start; max-width: min(100%,820px); }.message-meta { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; }.message-meta strong { color: $text-secondary; font-size: 10px; }.agent-pill { padding: 2px 6px; border-radius: 8px; color: $primary-color; background: $primary-soft; font-size: 8px; font-weight: 800; }.agent-pill.dataset { color: #7c3aed; background: rgba(139,92,246,.1); }.agent-pill.training { color: #0284c7; background: rgba(14,165,233,.1); }.agent-pill.catalog { color: #b45309; background: rgba(245,158,11,.1); }.agent-pill.knowledge { color: #047857; background: rgba(16,185,129,.1); }.message-bubble { min-width: 70px; padding: 14px 16px; border: 1px solid $border-color; border-radius: 7px 18px 18px 18px; background: #fff; box-shadow: 0 8px 24px rgba(15,23,42,.05); }.message-row.user .message-bubble { border: 1px solid rgba(0,113,227,.16); border-radius: 7px 18px 18px 18px; color: $text-primary; background: linear-gradient(135deg,rgba(236,246,255,.98),rgba(246,249,255,.98)); box-shadow: none; }.message-content { font-size: 13px; line-height: 1.72; overflow-wrap: anywhere; }.message-content :deep(p) { margin: 0 0 9px; }.message-content :deep(p:last-child) { margin-bottom: 0; }.message-content :deep(h1),.message-content :deep(h2),.message-content :deep(h3),.message-content :deep(h4) { margin: 16px 0 9px; color: $text-primary; font-size: 15px; line-height: 1.35; letter-spacing: -.01em; }.message-content :deep(h1:first-child),.message-content :deep(h2:first-child),.message-content :deep(h3:first-child),.message-content :deep(h4:first-child) { margin-top: 0; }.message-content :deep(hr) { height: 1px; margin: 15px 0; border: 0; background: $border-color; }.message-content :deep(ul),.message-content :deep(ol) { margin: 8px 0; padding-left: 20px; }.message-content :deep(li + li) { margin-top: 4px; }.message-content :deep(.markdown-table-wrap) { max-width: 100%; margin: 12px 0; overflow-x: auto; border: 1px solid $border-color; border-radius: 12px; background: $surface-color; box-shadow: inset 0 1px 0 rgba(255,255,255,.7); }.message-content :deep(table) { width: 100%; min-width: 420px; border-collapse: separate; border-spacing: 0; font-size: 12px; line-height: 1.5; }.message-content :deep(th),.message-content :deep(td) { padding: 9px 12px; border: 0; border-bottom: 1px solid $border-color; text-align: left; vertical-align: top; }.message-content :deep(th) { color: $text-secondary; background: $surface-muted; font-size: 10px; font-weight: 800; letter-spacing: .02em; white-space: nowrap; }.message-content :deep(th + th),.message-content :deep(td + td) { border-left: 1px solid $border-color; }.message-content :deep(tr:last-child td) { border-bottom: 0; }.message-content :deep(td:first-child) { width: 34%; color: $text-secondary; font-weight: 700; white-space: nowrap; }.message-files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }.message-files span { display: inline-flex; align-items: center; gap: 5px; max-width: 220px; padding: 5px 8px; border-radius: 8px; color: inherit; background: rgba(148,163,184,.13); font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.thinking { display: flex; align-items: center; gap: 5px; min-height: 24px; }.thinking span { width: 6px; height: 6px; border-radius: 50%; background: $primary-color; animation: thinking 1.1s infinite; }.thinking span:nth-child(2) { animation-delay: .15s; }.thinking span:nth-child(3) { animation-delay: .3s; }.thinking em { margin-left: 5px; color: $text-placeholder; font-size: 9px; font-style: normal; }.tool-state { display: inline-flex; align-items: center; gap: 8px; padding: 7px 9px; border-radius: 10px; color: #b45309; background: rgba(245,158,11,.09); }.tool-state > span { display: flex; flex-direction: column; font-size: 10px; font-weight: 800; }.tool-state small { color: #d97706; font-size: 8px; font-weight: 500; }.handoff-action { margin-top: 12px; }.detection-result { margin-top: 10px; }.stream-cursor { display: inline-block; width: 2px; height: 1em; margin-left: 3px; vertical-align: -2px; background: $primary-color; animation: blink .8s infinite; }
.composer { padding: 10px max(24px,calc((100% - 820px)/2)) 16px; border-top: 1px solid $border-color; background: rgba(255,255,255,.88); }.attachment-tray { display: flex; gap: 7px; overflow-x: auto; padding-bottom: 7px; }.attachment-tray > span { min-width: 130px; max-width: 210px; height: 34px; display: grid; grid-template-columns: 26px minmax(0,1fr) 20px; align-items: center; gap: 5px; padding: 3px 5px; border: 1px solid $border-color; border-radius: 9px; background: $surface-muted; }.attachment-tray img { width: 26px; height: 26px; object-fit: cover; border-radius: 6px; }.attachment-tray b { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.attachment-tray button { border: 0; color: $text-placeholder; background: transparent; cursor: pointer; }.composer-box { padding: 10px 11px 8px; border: 1px solid $border-color; border-radius: 17px; background: #fff; box-shadow: 0 12px 28px rgba(15,23,42,.08); transition: .2s; }.composer-box:focus-within { border-color: rgba(0,113,227,.55); box-shadow: 0 12px 30px rgba(0,113,227,.11),0 0 0 3px rgba(0,113,227,.08); }.composer textarea { width: 100%; min-height: 34px; max-height: 110px; padding: 4px; resize: none; border: 0; outline: 0; color: $text-primary; background: transparent; font: inherit; font-size: 12px; line-height: 1.5; }.composer-actions { display: flex; align-items: center; gap: 6px; }.composer-actions input { display: none; }.composer-actions > span { flex: 1; color: $text-placeholder; font-size: 8px; }.send-button { box-shadow: 0 7px 15px rgba(0,113,227,.2); }
.insight-panel section + section { margin-top: 18px; padding-top: 8px; border-top: 1px solid $border-color; }.agent-list { display: flex; flex-direction: column; gap: 6px; }.agent-item { display: grid; grid-template-columns: 32px minmax(0,1fr) 7px; align-items: center; gap: 8px; padding: 7px; border-radius: 11px; transition: .2s; }.agent-item.active { background: #fff; box-shadow: 0 8px 20px rgba(15,23,42,.06); }.agent-item > span { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 10px; color: #fff; background: $primary-color; }.agent-item > span.dataset { background: #8b5cf6; }.agent-item > span.training { background: #0ea5e9; }.agent-item > span.catalog { background: #f59e0b; }.agent-item > span.knowledge { background: #10b981; }.agent-item div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }.agent-item strong { font-size: 11px; }.agent-item small { overflow: hidden; color: $text-placeholder; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.agent-item > i { width: 6px; height: 6px; border-radius: 50%; background: $border-strong; }.agent-item.active > i { background: $success-color; box-shadow: 0 0 0 4px rgba(16,185,129,.1); }.pending-list { display: flex; flex-direction: column; gap: 6px; }.pending-list button { display: grid; grid-template-columns: 28px minmax(0,1fr) 15px; align-items: center; gap: 7px; padding: 8px; border: 1px solid $border-color; border-radius: 11px; background: #fff; text-align: left; cursor: pointer; }.pending-list button > span { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px; color: #fff; background: #f59e0b; font-size: 9px; font-weight: 900; }.pending-list button > span.r3 { background: #ef4444; }.pending-list div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }.pending-list strong,.pending-list small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.pending-list strong { font-size: 10px; }.pending-list small { color: $text-placeholder; font-size: 8px; }.pending-list .el-icon { color: $text-placeholder; }.pending-empty { display: flex; align-items: center; gap: 7px; padding: 12px; border-radius: 11px; color: $text-secondary; background: rgba(16,185,129,.07); font-size: 10px; }.pending-empty .el-icon { color: $success-color; }.safety-card { display: flex; gap: 8px; padding: 11px; border: 1px solid rgba(0,113,227,.12); border-radius: 12px; background: linear-gradient(145deg,rgba(0,113,227,.07),rgba(124,58,237,.05)); }.safety-card > .el-icon { flex: 0 0 auto; color: $primary-color; }.safety-card div { display: flex; flex-direction: column; gap: 4px; }.safety-card strong { font-size: 10px; }.safety-card small { color: $text-secondary; font-size: 9px; line-height: 1.55; }

/* GPT 风格消息流：用户在右侧，Agent 回复保留为无气泡的阅读内容。 */
.message-row { display: block; }.message-row.user { display: block; }.message-row.user > .message-column { display: block; max-width: min(78%, 680px); margin-left: auto; }.message-row.user .message-bubble { border: 1px solid $border-color; border-radius: 22px 22px 6px 22px; color: $text-primary; background: #fff; box-shadow: 0 8px 24px rgba(15,23,42,.05); }
.message-row.assistant .message-column { max-width: min(100%,820px); }.message-row.assistant .message-bubble { min-width: 0; padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; }.message-row.assistant .message-files { margin-top: 11px; }.agent-activity { display: flex; align-items: center; min-height: 28px; gap: 8px; margin-bottom: 9px; color: $text-secondary; font-size: 10px; }.agent-activity > i { width: 16px; height: 1px; background: $border-strong; }.agent-activity .agent-pill { display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; font-size: 9px; }.agent-activity .tool-state { display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; border: 1px solid rgba(245,158,11,.2); border-radius: 999px; color: #a16207; background: rgba(245,158,11,.09); font-size: 10px; font-weight: 700; }.agent-activity .tool-state small { color: inherit; font-size: 9px; font-weight: 500; }.activity-status { color: $text-placeholder; font-size: 10px; }.message-row.assistant .thinking { min-height: 28px; }.message-row.assistant .thinking em { font-size: 10px; }
.panel-title,.insight-toolbar { font-size: 11px; }.session-copy strong { font-size: 11px; }.session-copy small { font-size: 9px; }.session-empty { font-size: 11px; }.privacy-note { font-size: 10px; }
@keyframes thinking { 0%,70%,100% { opacity:.25; transform:translateY(0) } 35% { opacity:1; transform:translateY(-2px) } } @keyframes blink { 0%,45% { opacity:1 } 46%,100% { opacity:0 } }
@media (max-width: 1180px) { .chat-layout { --session-column: 220px; --insight-column: 252px; } }
@media (max-width: 920px) { .chat-layout { --session-column: 64px; --insight-column: 64px; } .chat-layout:not(.sessions-collapsed) { --session-column: 220px; } .chat-layout:not(.insights-collapsed) { --insight-column: 252px; } }
@media (max-width: 820px) { .page-header { align-items: flex-start; }.header-state { display: none; }.chat-layout { display: flex; flex-direction: column; overflow: visible; }.session-panel,.insight-panel { width: 100%; border: 0; }.session-panel { border-bottom: 1px solid $border-color; }.insight-panel { border-top: 1px solid $border-color; }.session-panel.collapsed,.insight-panel.collapsed { width: 100%; min-height: 64px; }.session-panel.collapsed .sidebar-toolbar,.insight-panel.collapsed .insight-toolbar { flex-direction: row; justify-content: flex-start; }.conversation-panel { min-height: 560px; }.quick-grid { grid-template-columns: 1fr; }.message-list,.composer { padding-left: 16px; padding-right: 16px; } }
:global(html.dark .page-header) { color: #f5f5f7; background: rgba(28,28,30,.82); border-color: rgba(255,255,255,.1); box-shadow: 0 16px 48px rgba(0,0,0,.28); }
:global(html.dark .header-state) { background: rgba(44,44,46,.82); border-color: rgba(255,255,255,.1); }
:global(html.dark .chat-layout) { color: #f5f5f7; background: rgba(28,28,30,.84); border-color: rgba(255,255,255,.1); box-shadow: 0 24px 64px rgba(0,0,0,.34); }
:global(html.dark .session-panel),
:global(html.dark .insight-panel) { background: rgba(22,22,24,.9); border-color: rgba(255,255,255,.09); }
:global(html.dark .panel-toggle) { color: #a1a1aa; border-color: rgba(255,255,255,.12); background: rgba(44,44,46,.84); }
:global(html.dark .session-item:hover),
:global(html.dark .session-item.active),
:global(html.dark .agent-item.active) { color: #f5f5f7; background: #2c2c2e; box-shadow: 0 8px 22px rgba(0,0,0,.22); }
:global(html.dark .session-icon) { background: #3a3a3c; }
:global(html.dark .privacy-note),
:global(html.dark .pending-empty) { background: rgba(48,209,88,.1); }
:global(html.dark .quick-grid button),
:global(html.dark .message-bubble),
:global(html.dark .pending-list button) { color: #f5f5f7; background: rgba(44,44,46,.88); border-color: rgba(255,255,255,.1); }
:global(html.dark .quick-grid button:hover) { border-color: rgba(10,132,255,.45); box-shadow: 0 12px 28px rgba(0,0,0,.28); }
:global(html.dark .message-row.user .message-bubble) { color: #f5f5f7; border-color: transparent; background: #2f2f31; }
:global(html.dark .message-content h1),
:global(html.dark .message-content h2),
:global(html.dark .message-content h3),
:global(html.dark .message-content h4) { color: #f5f5f7; }
:global(html.dark .message-content .markdown-table-wrap) { border-color: rgba(255,255,255,.1); background: #2c2c2e; box-shadow: none; }
:global(html.dark .message-content th),
:global(html.dark .message-content td) { border-color: rgba(255,255,255,.1); }
:global(html.dark .message-content th) { color: #a1a1aa; background: #3a3a3c; }
:global(html.dark .message-content td:first-child) { color: #d1d1d6; }
:global(html.dark .agent-activity .tool-state) { color: #ffd60a; border-color: rgba(255,214,10,.22); background: rgba(255,214,10,.1); }
:global(html.dark .composer-box) { background: #2c2c2e; border-color: rgba(255,255,255,.12); box-shadow: 0 12px 30px rgba(0,0,0,.28); }
:global(html.dark .composer textarea) { color: #f5f5f7; }
:global(html.dark .attachment-tray > span) { background: #2c2c2e; border-color: rgba(255,255,255,.1); }
:global(html.dark .safety-card) { background: linear-gradient(145deg,rgba(10,132,255,.14),rgba(191,90,242,.1)); border-color: rgba(10,132,255,.2); }
</style>
