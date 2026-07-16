<template>
  <div class="workspace" @dragover.prevent @drop.prevent="handleDrop">
    <header class="workspace-header">
      <div>
        <span class="kicker">VisionPay Intelligence</span>
        <h1>商品检测</h1>
        <p>添加图片或视频，快速生成识别与结算结果。</p>
      </div>
      <div class="header-actions">
        <span :class="['agent-status', { ready: agentStatus.configured }]">
          <i></i>{{ agentStatus.configured ? agentStatus.model : 'Agent 未配置' }}
        </span>
      </div>
    </header>

    <div :class="['workspace-grid', { 'sessions-collapsed': sessionsCollapsed, 'controls-collapsed': controlsCollapsed }]">
      <aside :class="['session-sidebar', { collapsed: sessionsCollapsed }]">
        <div class="session-toolbar">
          <el-tooltip content="创建新对话" placement="right" :show-arrow="false" :disabled="!sessionsCollapsed">
            <el-button class="new-chat-button" :icon="Plus" :circle="sessionsCollapsed" aria-label="创建新对话" @click="createNewChat">
              <span v-if="!sessionsCollapsed">新对话</span>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="sessionsCollapsed ? '展开历史对话' : '收起历史对话'" placement="right" :show-arrow="false">
            <el-button
              class="panel-toggle"
              :icon="sessionsCollapsed ? DArrowRight : DArrowLeft"
              circle
              :aria-label="sessionsCollapsed ? '展开历史对话' : '收起历史对话'"
              :aria-expanded="!sessionsCollapsed"
              @click="sessionsCollapsed = !sessionsCollapsed"
            />
          </el-tooltip>
        </div>
        <div v-show="!sessionsCollapsed" class="session-heading">
          <span>历史对话</span>
          <el-button
            text
            :icon="Refresh"
            :loading="sessionLoading"
            aria-label="刷新历史"
            @click="loadSessions"
          />
        </div>
        <div v-show="!sessionsCollapsed" class="session-list" v-loading="sessionLoading">
          <button
            v-for="session in agentStore.sessions"
            :key="session.session_uuid"
            type="button"
            :class="['session-item', { active: session.session_uuid === agentStore.currentSessionId }]"
            @click="openSession(session.session_uuid)"
          >
            <el-icon><ChatLineSquare /></el-icon>
            <span><strong>{{ session.title }}</strong><small>{{ formatSessionTime(session.last_message_at || session.created_at) }}</small></span>
            <el-tooltip content="删除对话" placement="right" :show-arrow="false">
              <i class="session-delete" role="button" tabindex="0" @click.stop="removeSession(session)" @keydown.enter.stop="removeSession(session)"><el-icon><Delete /></el-icon></i>
            </el-tooltip>
          </button>
          <div v-if="!sessionLoading && !agentStore.sessions.length" class="no-sessions">暂无历史对话</div>
        </div>
      </aside>

      <main class="conversation-panel">
        <IpCameraDetectionPanel
          v-if="inputMode === 'camera'"
          class="workspace-camera"
          :scene-id="sceneId"
          :conf="confidence"
          :iou="iou"
          auto-start
        />
        <div v-else ref="messageListRef" class="message-list">
          <Transition name="new-chat">
            <section v-if="!agentStore.messages.length" class="empty-state">
              <div class="empty-mark"><img src="/favicon.svg" alt="" /></div>
              <span class="empty-eyebrow">Vision Agent</span>
              <h2>从一张商品图片开始</h2>
              <p class="empty-copy">上传素材后，VisionPay 会识别商品、汇总数量并生成结算清单。</p>
              <div class="starter-grid">
                <button type="button" @click="inputText = '识别附件中的商品，并按类别汇总数量'">识别并汇总</button>
                <button type="button" @click="inputText = '检查识别结果中置信度较低的商品'">检查低置信度</button>
                <button type="button" @click="inputText = '根据识别结果生成结算商品清单'">生成结算清单</button>
              </div>
            </section>
          </Transition>

          <article v-for="(message, index) in agentStore.messages" :key="index" :class="['message-row', message.role]">
            <div class="avatar"><el-icon><User v-if="message.role === 'user'" /><Cpu v-else /></el-icon></div>
            <div class="message-body">
              <div class="message-label">{{ message.role === 'user' ? '你' : agentName(message.agent) }}</div>
              <div v-if="message.content || message.loading || message.tool || message.files?.length || message.confirmation" class="message-bubble">
                <div v-if="message.content" class="message-content" v-html="message.role === 'assistant' ? renderMarkdown(message.content) : escapeText(message.content)"></div>
                <span v-if="message.role === 'assistant' && message.loading && message.content" class="stream-cursor"></span>
                <div v-if="message.files?.length" class="message-files">
                  <span v-for="file in message.files" :key="file.name"><el-icon><Document /></el-icon>{{ file.name }}</span>
                </div>
                <div v-if="message.loading && !message.content" class="thinking" aria-label="Agent 正在思考"><span></span><span></span><span></span></div>
                <div v-if="message.tool" class="tool-state"><el-icon><Operation /></el-icon>{{ toolName(message.tool) }} 正在处理</div>
                <el-button
                  v-if="message.role === 'assistant' && message.handoff?.page_url"
                  class="handoff-button"
                  type="primary"
                  @click="openHandoff(message.handoff.page_url)"
                >
                  前往人工添加样品
                </el-button>
                <section v-if="message.role === 'assistant' && message.confirmation" class="confirmation-card">
                  <div class="confirmation-heading">
                    <div>
                      <span>{{ message.confirmation.risk_level }} · 待确认操作</span>
                      <strong>{{ message.confirmation.impact?.title || message.confirmation.action }}</strong>
                    </div>
                    <el-tag :type="confirmationTagType(message.confirmation.status)" effect="light">
                      {{ confirmationStatusText(message.confirmation.status) }}
                    </el-tag>
                  </div>
                  <p>{{ message.confirmation.impact?.summary }}</p>
                  <dl v-if="message.confirmation.impact?.changes">
                    <template v-for="(value, key) in message.confirmation.impact.changes" :key="key">
                      <dt>{{ impactKeyText(key) }}</dt><dd>{{ impactValueText(value) }}</dd>
                    </template>
                  </dl>
                  <ul v-if="message.confirmation.impact?.warnings?.length">
                    <li v-for="warning in message.confirmation.impact.warnings" :key="warning">{{ warning }}</li>
                  </ul>
                  <div v-if="message.confirmation.status === 'pending'" class="confirmation-actions">
                    <el-button
                      type="danger"
                      :loading="message.confirmation.confirming"
                      @click="confirmPendingOperation(message)"
                    >确认执行</el-button>
                    <el-button
                      :disabled="message.confirmation.confirming"
                      @click="cancelPendingOperation(message)"
                    >取消</el-button>
                  </div>
                  <pre v-if="message.confirmation.result" class="confirmation-result">{{ impactValueText(message.confirmation.result) }}</pre>
                  <p v-if="message.confirmation.error_message" class="confirmation-error">{{ message.confirmation.error_message }}</p>
                </section>
              </div>
              <DetectionResultCard v-if="message.result" :result="message.result" />
            </div>
          </article>
        </div>

        <footer v-if="inputMode !== 'camera'" class="composer">
          <div v-if="selectedFiles.length" class="selected-files">
            <span v-for="(item, index) in selectedFiles" :key="item.id">
              <img v-if="item.preview" :src="item.preview" alt="" />
              <el-icon v-else><FolderOpened /></el-icon>
              <b :title="item.file.name">{{ item.file.name }}</b>
              <button type="button" aria-label="移除附件" @click="removeFile(index)"><el-icon><Close /></el-icon></button>
            </span>
          </div>
          <div class="composer-row" @paste="handlePaste">
            <input ref="singleInputRef" class="file-input" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" @change="handleFileInput($event, 'single')" />
            <input ref="batchInputRef" class="file-input" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" multiple @change="handleFileInput($event, 'batch')" />
            <input ref="zipInputRef" class="file-input" type="file" accept=".zip,application/zip" @change="handleFileInput($event, 'zip')" />
            <input ref="videoInputRef" class="file-input" type="file" accept="video/mp4,video/quicktime,video/x-msvideo,.mkv" @change="handleFileInput($event, 'video')" />
            <el-tooltip content="按当前模式添加文件" placement="top" :show-arrow="false"><el-button :icon="Paperclip" circle :disabled="busy" @click="openModePicker(inputMode)" /></el-tooltip>
            <el-input v-model="inputText" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" resize="none" placeholder="向识别 Agent 发出指令，或直接粘贴图片和文件" :disabled="busy" @keydown.enter.exact.prevent="sendToAgent" />
            <el-tooltip :content="busy ? '停止响应' : '发送给 Agent'" placement="top" :show-arrow="false">
              <el-button class="send-button" :type="busy ? 'danger' : 'primary'" :icon="busy ? VideoPause : Promotion" circle :disabled="!busy && !canSend" @click="busy ? stopStream() : sendToAgent()" />
            </el-tooltip>
          </div>
        </footer>
      </main>

      <aside :class="['control-rail', { collapsed: controlsCollapsed }]">
        <div class="rail-toolbar">
          <span v-show="!controlsCollapsed">识别设置</span>
          <el-tooltip :content="controlsCollapsed ? '展开识别设置' : '收起识别设置'" placement="left" :show-arrow="false">
            <el-button
              class="panel-toggle"
              :icon="controlsCollapsed ? DArrowLeft : DArrowRight"
              circle
              :aria-label="controlsCollapsed ? '展开识别设置' : '收起识别设置'"
              :aria-expanded="!controlsCollapsed"
              @click="controlsCollapsed = !controlsCollapsed"
            />
          </el-tooltip>
        </div>
        <div v-show="!controlsCollapsed" class="control-rail-body">
          <section class="rail-section">
            <div class="section-title"><span>添加素材</span><em>{{ selectedFiles.length }}</em></div>
            <button class="drop-zone" type="button" :disabled="busy" @click="openModePicker(inputMode)">
              <el-icon><UploadFilled /></el-icon><strong>{{ modeCopy.title }}</strong><span>{{ modeCopy.hint }}</span>
            </button>
            <div class="input-modes">
              <button type="button" :class="{ active: inputMode === 'single' }" @click="selectMode('single')"><el-icon><Picture /></el-icon>单图</button>
              <button type="button" :class="{ active: inputMode === 'batch' }" @click="selectMode('batch')"><el-icon><Files /></el-icon>多图</button>
              <button type="button" :class="{ active: inputMode === 'zip' }" @click="selectMode('zip')"><el-icon><Folder /></el-icon>ZIP</button>
              <button type="button" :class="{ active: inputMode === 'video' }" @click="selectMode('video')"><el-icon><VideoPlay /></el-icon>视频</button>
              <button type="button" :class="{ active: inputMode === 'camera' }" @click="selectMode('camera')"><el-icon><VideoCamera /></el-icon>实时</button>
            </div>
          </section>

          <section class="rail-section parameters">
            <div class="section-title"><span>推理参数</span></div>
            <label>置信度 <strong>{{ Math.round(confidence * 100) }}%</strong></label>
            <el-slider v-model="confidence" :min="0.05" :max="0.95" :step="0.05" :show-tooltip="false" :disabled="inputMode === 'camera'" />
            <label>NMS IoU <strong>{{ Math.round(iou * 100) }}%</strong></label>
            <el-slider v-model="iou" :min="0.05" :max="0.95" :step="0.05" :show-tooltip="false" :disabled="inputMode === 'camera'" />
            <label>场景 ID <el-tooltip content="留空时使用首个可用场景" :show-arrow="false"><el-icon><QuestionFilled /></el-icon></el-tooltip></label>
            <el-input-number v-model="sceneId" :min="1" :controls="false" placeholder="自动" :disabled="inputMode === 'camera'" />
          </section>

          <section v-if="inputMode !== 'camera'" class="rail-section action-section">
            <el-button type="primary" :icon="Aim" :loading="directLoading" :disabled="!selectedFiles.length || agentStore.isLoading" @click="runDirectDetection">开始识别</el-button>
            <span>使用当前参数分析所选素材</span>
          </section>

          <section v-if="latestResult && inputMode !== 'camera'" class="rail-section summary-section">
            <div class="section-title"><span>本次汇总</span><em>#{{ latestResult.task_id }}</em></div>
            <div class="summary-metrics"><div><strong>{{ latestResult.total_objects }}</strong><span>商品</span></div><div><strong>{{ latestResult.total_images }}</strong><span>图片</span></div></div>
            <div v-if="latestResult.price_summary" class="summary-price">
              <span>检测总价</span><strong>¥ {{ Number(latestResult.price_summary.total_price || 0).toFixed(2) }}</strong>
              <small v-if="!latestResult.price_summary.pricing_complete">{{ latestResult.price_summary.unpriced_objects }} 件商品未定价</small>
            </div>
            <ul><li v-for="(count, name) in latestResult.class_counts" :key="name"><span>{{ name }}</span><strong>{{ count }}</strong></li></ul>
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
import { Aim, ChatLineSquare, Close, Cpu, DArrowLeft, DArrowRight, Delete, Document, Files, Folder, FolderOpened, Operation, Paperclip, Picture, Plus, Promotion, QuestionFilled, Refresh, UploadFilled, User, VideoCamera, VideoPause, VideoPlay, View } from '@element-plus/icons-vue'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import IpCameraDetectionPanel from '@/components/IpCameraDetectionPanel.vue'
import { createDetectionSessionApi, deleteDetectionSessionApi, detectBatchApi, detectSingleApi, detectVideoApi, detectZipApi, getAgentStatusApi, getDetectionSessionApi, getDetectionSessionsApi, getVideoStatusApi, saveDetectionExchangeApi, uploadChatFilesApi } from '@/api/detection'
import { cancelAgentOperationApi, confirmAgentOperationApi, getAgentOperationApi, rotateAgentOperationTokenApi } from '@/api/agentOperations'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import { streamChat } from '@/utils/stream'

const agentStore = useAgentStore()
const router = useRouter()
agentStore.newChat()
const inputText = ref('')
const selectedFiles = ref([])
const confidence = ref(0.25)
const iou = ref(0.45)
const sceneId = ref(undefined)
const directLoading = ref(false)
const singleInputRef = ref(null)
const batchInputRef = ref(null)
const zipInputRef = ref(null)
const videoInputRef = ref(null)
const messageListRef = ref(null)
const agentStatus = ref({ configured: false, model: 'DeepSeek' })
const latestResult = ref(null)
const inputMode = ref('single')
const sessionLoading = ref(false)
const sessionsCollapsed = ref(false)
const controlsCollapsed = ref(false)
const busy = computed(() => directLoading.value || agentStore.isLoading)
const canSend = computed(() => inputText.value.trim() || selectedFiles.value.length)
const clipboardExtensionByType = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/bmp': '.bmp',
  'image/webp': '.webp',
  'video/mp4': '.mp4',
  'video/quicktime': '.mov',
  'video/x-msvideo': '.avi',
  'video/x-matroska': '.mkv',
  'application/zip': '.zip',
  'application/x-zip-compressed': '.zip',
}
const modeCopy = computed(() => ({
  single: { title: '选择一张商品图片', hint: 'JPG / PNG / BMP / WEBP' },
  batch: { title: '选择多张商品图片', hint: '最多 30 张图片' },
  zip: { title: '选择一个 ZIP 文件', hint: 'ZIP 内最多 30 张图片' },
  video: { title: '选择一个商品视频', hint: 'MP4 / AVI / MOV / MKV · 最大 50MB' },
  camera: { title: 'IP Webcam 实时检测', hint: 'CPU 512 × 512 · 跨帧稳定' },
})[inputMode.value])

onMounted(async () => {
  try { agentStatus.value = await getAgentStatusApi() } catch { /* auth interceptor reports errors */ }
  await loadSessions()
})
onBeforeUnmount(() => { stopStream(); clearSelectedFiles() })
function escapeText(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML.replace(/\n/g, '<br>') }
function toolName(name) { return ({ detect_single_product_image: '单图商品识别', detect_product_images: '批量商品识别', detect_product_zip: 'ZIP 商品识别', detect_product_video: '视频关键帧识别' })[name] || name }
function agentName(name) { return ({ detection: 'Detection Agent', dataset: 'Dataset Agent', training: 'Training Agent', catalog: 'Catalog Agent', knowledge: 'Knowledge Agent' })[name] || 'VisionPay Agent' }
function openHandoff(pageUrl) { if (pageUrl) router.push(pageUrl) }
function lastAssistantAgent() { return [...agentStore.messages].reverse().find((message) => message.role === 'assistant' && message.agent)?.agent || '' }
function confirmationStatusText(status) { return ({ pending: '等待确认', executing: '执行中', completed: '已完成', failed: '执行失败', cancelled: '已取消', expired: '已过期' })[status] || status }
function confirmationTagType(status) { return ({ pending: 'warning', executing: 'primary', completed: 'success', failed: 'danger', cancelled: 'info', expired: 'info' })[status] || 'info' }
function impactKeyText(key) { return ({ images: '图片数', annotations: '标注数', classes: '类别数', training_tasks: '训练引用', model_versions: '模型引用', status: '状态变化', old_price: '原价', new_price: '新价', old_model_version: '原模型', new_model_version: '新模型', affected_images: '受影响图片', annotations_deleted: '删除标注', mixed_scene_images_retained: '保留多商品场景', classes_reindexed: '重排类别', epochs: '训练轮数', batch_size: '批次大小', img_size: '图片尺寸', device: '训练设备' })[key] || key }
function impactValueText(value) {
  if (value === null || value === undefined) return '无'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}
function operationIdempotencyKey(operation) {
  if (!operation.executionKey) operation.executionKey = `confirm-${operation.operation_uuid}-${crypto.randomUUID?.() || Date.now()}`
  return operation.executionKey
}
async function confirmPendingOperation(message) {
  const operation = message.confirmation
  if (!operation || operation.status !== 'pending' || operation.confirming) return
  operation.confirming = true
  try {
    if (!operation.confirmation_token) {
      const refreshed = await rotateAgentOperationTokenApi(operation.operation_uuid)
      operation.confirmation_token = refreshed.confirmation_token
      operation.token_expires_at = refreshed.token_expires_at
    }
    const result = await confirmAgentOperationApi(
      operation.operation_uuid,
      operation.confirmation_token,
      operationIdempotencyKey(operation),
    )
    Object.assign(operation, result, { confirming: false, confirmation_token: undefined })
    ElMessage.success(result.replayed ? '操作已完成，本次返回幂等结果' : '操作执行成功')
  } catch (error) {
    operation.confirming = false
    operation.error_message = error?.response?.data?.detail || error.message || '操作执行失败'
    try {
      const current = await getAgentOperationApi(operation.operation_uuid)
      Object.assign(operation, current, { confirming: false })
    } catch { /* 保留首次错误，避免同步失败覆盖原因 */ }
  }
}
async function cancelPendingOperation(message) {
  const operation = message.confirmation
  if (!operation || operation.status !== 'pending') return
  try {
    const result = await cancelAgentOperationApi(operation.operation_uuid)
    Object.assign(operation, result, { confirmation_token: undefined })
    ElMessage.info('已取消待确认操作')
  } catch (error) {
    operation.error_message = error?.response?.data?.detail || error.message || '取消失败'
  }
}
async function scrollBottom() { await nextTick(); if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight }

async function loadSessions() {
  sessionLoading.value = true
  try { agentStore.sessions = (await getDetectionSessionsApi()).items }
  finally { sessionLoading.value = false }
}
async function ensureSession() {
  if (agentStore.currentSessionId) return agentStore.currentSessionId
  const session = await createDetectionSessionApi()
  agentStore.currentSessionId = session.session_uuid
  return session.session_uuid
}
function createNewChat() {
  stopStream()
  agentStore.currentSessionId = null
  agentStore.messages = []
  latestResult.value = null
  inputText.value = ''
  clearSelectedFiles()
}
async function openSession(sessionUuid) {
  if (busy.value || sessionUuid === agentStore.currentSessionId && agentStore.messages.length) return
  stopStream()
  sessionLoading.value = true
  try {
    const data = await getDetectionSessionApi(sessionUuid)
    agentStore.currentSessionId = sessionUuid
    agentStore.messages = data.messages.map((message) => ({ ...message, loading: false }))
    await Promise.allSettled(agentStore.messages
      .filter((message) => message.confirmation?.operation_uuid)
      .map(async (message) => {
        const current = await getAgentOperationApi(message.confirmation.operation_uuid)
        Object.assign(message.confirmation, current)
      }))
    latestResult.value = [...agentStore.messages].reverse().find((message) => message.result)?.result || null
    await scrollBottom()
  } finally { sessionLoading.value = false }
}
async function removeSession(session) {
  try {
    await ElMessageBox.confirm(`确定删除“${session.title}”吗？`, '删除对话', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await deleteDetectionSessionApi(session.session_uuid)
    agentStore.sessions = agentStore.sessions.filter((item) => item.session_uuid !== session.session_uuid)
    if (agentStore.currentSessionId === session.session_uuid) {
      agentStore.currentSessionId = null
      agentStore.messages = []
      if (agentStore.sessions.length) await openSession(agentStore.sessions[0].session_uuid)
      else createNewChat()
    }
  } catch (error) { if (error !== 'cancel' && error !== 'close') throw error }
}
function formatSessionTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const today = new Date()
  const timeText = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (date.toDateString() === today.toDateString()) return timeText
  const dateOptions = { month: '2-digit', day: '2-digit' }
  if (date.getFullYear() !== today.getFullYear()) dateOptions.year = 'numeric'
  return `${date.toLocaleDateString('zh-CN', dateOptions)} ${timeText}`
}
function selectMode(mode) {
  if (busy.value) return
  if (mode === 'camera' && confidence.value < 0.30) confidence.value = 0.30
  inputMode.value = mode
  clearSelectedFiles()
  if (mode !== 'camera') openModePicker(mode)
}
function openModePicker(mode) {
  const refs = { single: singleInputRef, batch: batchInputRef, zip: zipInputRef, video: videoInputRef }
  refs[mode]?.value?.click()
}
function selectFiles(files, mode = inputMode.value) {
  const expression = mode === 'zip' ? /\.zip$/i : mode === 'video' ? /\.(mp4|avi|mov|mkv)$/i : /\.(jpe?g|png|bmp|webp)$/i
  const incoming = [...files].filter((file) => expression.test(file.name))
  const next = mode === 'batch' ? incoming.slice(0, 30) : incoming.slice(0, 1)
  clearSelectedFiles()
  selectedFiles.value = next.map((file) => ({ id: `${file.name}-${file.lastModified}`, file, preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : '' }))
  if (files.length && !incoming.length) ElMessage.warning(mode === 'zip' ? '请选择 ZIP 文件' : mode === 'video' ? '请选择 MP4、AVI、MOV 或 MKV 视频' : '请选择商品图片')
  if (mode === 'video' && next[0]?.size > 50 * 1024 * 1024) {
    clearSelectedFiles()
    ElMessage.warning('视频文件不能超过 50MB')
  }
}
function handleFileInput(event, mode) { inputMode.value = mode; selectFiles(event.target.files, mode); event.target.value = '' }
function normalizeClipboardFile(file, index) {
  if (/\.[a-z0-9]+$/i.test(file.name || '')) return file
  const extension = clipboardExtensionByType[file.type]
  if (!extension) return file
  const baseName = (file.name || '').trim() || `clipboard-${Date.now()}-${index + 1}`
  return new File([file], `${baseName}${extension}`, { type: file.type, lastModified: file.lastModified || Date.now() })
}
function pastedFileMode(files) {
  const kinds = new Set(files.map((file) => {
    if (/\.(jpe?g|png|bmp|webp)$/i.test(file.name)) return 'image'
    if (/\.(mp4|avi|mov|mkv)$/i.test(file.name)) return 'video'
    if (/\.zip$/i.test(file.name)) return 'zip'
    return 'unsupported'
  }))
  if (kinds.has('unsupported')) return null
  if (kinds.size > 1) return 'mixed'
  const [kind] = kinds
  if (kind === 'image') return files.length > 1 ? 'batch' : 'single'
  return kind
}
function handlePaste(event) {
  const clipboard = event.clipboardData
  if (!clipboard) return
  const rawFiles = clipboard.files?.length
    ? [...clipboard.files]
    : [...(clipboard.items || [])].filter((item) => item.kind === 'file').map((item) => item.getAsFile()).filter(Boolean)
  if (!rawFiles.length) return

  event.preventDefault()
  if (busy.value) {
    ElMessage.warning('当前任务处理中，请完成或停止后再粘贴附件')
    return
  }

  const files = rawFiles.map(normalizeClipboardFile)
  const mode = pastedFileMode(files)
  if (!mode) {
    ElMessage.warning('仅支持粘贴 JPG、PNG、BMP、WEBP、ZIP、MP4、AVI、MOV 或 MKV 文件')
    return
  }
  if (mode === 'mixed') {
    ElMessage.warning('一次请粘贴同一类型的附件')
    return
  }

  inputMode.value = mode
  selectFiles(files, mode)
  if (selectedFiles.value.length) ElMessage.success(`已粘贴 ${selectedFiles.value.length} 个附件`)
}
function handleDrop(event) {
  if (busy.value) return
  const files = [...event.dataTransfer.files]
  const mode = files.some((file) => /\.(mp4|avi|mov|mkv)$/i.test(file.name)) ? 'video' : files.some((file) => /\.zip$/i.test(file.name)) ? 'zip' : files.length > 1 ? 'batch' : 'single'
  inputMode.value = mode
  selectFiles(files, mode)
}
function removeFile(index) { const [item] = selectedFiles.value.splice(index, 1); if (item?.preview) URL.revokeObjectURL(item.preview) }
function clearSelectedFiles() { selectedFiles.value.forEach((item) => item.preview && URL.revokeObjectURL(item.preview)); selectedFiles.value = [] }
function options() { return { conf: confidence.value, iou: iou.value, sceneId: sceneId.value } }

async function runDirectDetection() {
  if (!selectedFiles.value.length) return
  const sessionUuid = await ensureSession()
  directLoading.value = true
  const files = selectedFiles.value.map((item) => item.file)
  const fileMetadata = files.map((file) => ({ name: file.name }))
  const userContent = inputMode.value === 'video' ? `检测视频 ${files[0].name}` : '立即识别所选商品图片'
  agentStore.addMessage({ role: 'user', content: userContent, files: fileMetadata })
  const assistant = agentStore.addMessage({ role: 'assistant', content: '', loading: true, tool: 'yolo_direct', result: null })
  scrollBottom()
  try {
    let result
    if (inputMode.value === 'video') {
      const created = await detectVideoApi(files[0], options())
      assistant.content = '视频已上传，正在抽取关键帧…'
      result = await pollVideoResult(created.task_id, assistant)
    } else {
      result = inputMode.value === 'zip' ? await detectZipApi(files[0], options()) : inputMode.value === 'single' ? await detectSingleApi(files[0], options()) : await detectBatchApi(files, options())
    }
    assistant.content = result.source === 'video' ? `视频检测完成，共处理 ${result.processed_frames} 个关键帧，记录 ${result.total_objects} 次采样检测。` : `识别完成，共处理 ${result.total_images} 张图片，发现 ${result.total_objects} 件商品。`
    assistant.result = result; assistant.tool = ''; latestResult.value = result; clearSelectedFiles()
    await saveDetectionExchangeApi(sessionUuid, { user_content: userContent, assistant_content: assistant.content, files: fileMetadata, result })
    await loadSessions()
  } catch (error) { assistant.content = error?.response?.data?.detail || error?.message || '识别任务未完成，请检查模型、场景与后端日志。'; assistant.tool = '' }
  finally { assistant.loading = false; directLoading.value = false; scrollBottom() }
}

async function pollVideoResult(taskId, assistant) {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
    const status = await getVideoStatusApi(taskId)
    assistant.content = `${status.message || '视频处理中'}（${status.progress || 0}%）`
    scrollBottom()
    if (status.status === 'completed' && status.result) return status.result
    if (status.status === 'failed') throw new Error(status.message || '视频检测失败')
  }
  throw new Error('视频处理超时，请稍后在历史任务中查看')
}

async function sendToAgent() {
  if (!canSend.value || busy.value) return
  if (!localStorage.getItem('vp_agent_token')) {
    ElMessage.error('登录已过期，请重新登录')
    router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
    return
  }
  const sessionUuid = await ensureSession()
  const text = inputText.value.trim() || (lastAssistantAgent() === 'dataset'
    ? '我已选择样品图片，请继续添加样品流程'
    : '识别附件中的商品并汇总数量')
  const files = selectedFiles.value.map((item) => item.file)
  agentStore.addMessage({ role: 'user', content: text, files: files.map((file) => ({ name: file.name })) })
  const assistant = agentStore.addMessage({ role: 'assistant', content: '', loading: true, tool: '', result: null, agent: '' })
  inputText.value = ''; agentStore.setLoading(true); scrollBottom()
  try {
    const upload = files.length ? await uploadChatFilesApi(files) : { files: [] }
    const stream = streamChat('/api/chat/stream', { message: text, attachment_paths: upload.files.map((file) => file.path), attachment_names: files.map((file) => ({ name: file.name })), scene_id: sceneId.value, session_uuid: sessionUuid }, {
      onMessage(event) {
        if (event.type === 'routing') assistant.agent = event.agent
        if (event.type === 'text_chunk') assistant.content += event.content
        if (event.type === 'tool_call') assistant.tool = event.tool
        if (event.type === 'tool_result') assistant.tool = ''
        if (event.type === 'handoff_required') { assistant.handoff = event; assistant.tool = '' }
        if (event.type === 'confirmation_required') { assistant.confirmation = event.operation; assistant.tool = '' }
        if (event.type === 'detection_result') { assistant.result = event.result; latestResult.value = event.result; assistant.tool = '' }
        if (event.type === 'error') assistant.content += `\n\n${event.content}`
        scrollBottom()
      },
      onDone() { assistant.loading = false; assistant.tool = ''; agentStore.setLoading(false); agentStore.abortController = null; clearSelectedFiles(); loadSessions(); scrollBottom() },
      onError(error) { assistant.content = error.message; assistant.loading = false; agentStore.setLoading(false); agentStore.abortController = null; scrollBottom() },
    })
    agentStore.abortController = stream.stop
  } catch (error) { assistant.content = error.message || '附件上传失败'; assistant.loading = false; agentStore.setLoading(false) }
}
function stopStream() { agentStore.abort(); const last = agentStore.messages.at(-1); if (last?.role === 'assistant') { last.loading = false; last.tool = ''; if (!last.content) last.content = '已停止本次响应。' } }
</script>

<style lang="scss" scoped>
.workspace { height: 100%; min-height: 620px; display: flex; flex-direction: column; color: $text-primary; background: $bg-color; }
.workspace-header { min-height: 78px; padding: 14px 22px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid $border-color; border-radius: $border-radius-md $border-radius-md 0 0; background: $surface-color; box-shadow: $shadow-sm; }.workspace-header h1 { margin: 5px 0 0; font-family: 'Space Grotesk', 'DM Sans', sans-serif; font-size: 24px; line-height: 1.16; letter-spacing: 0; }.kicker { font-size: 11px; color: $primary-color; font-weight: 800; letter-spacing: 0.06em; }.header-actions { display: flex; align-items: center; gap: 10px; }.agent-status { display: flex; align-items: center; gap: 7px; font-size: 12px; color: $danger-color; font-weight: 700; }.agent-status i { width: 7px; height: 7px; border-radius: 50%; background: $danger-color; }.agent-status.ready { color: $success-color; }.agent-status.ready i { background: $success-color; box-shadow: 0 0 0 4px rgba(16, 185, 129, .12); }
.workspace-grid { min-height: 0; flex: 1; display: grid; grid-template-columns: 210px minmax(0, 1fr) 296px; border: 1px solid $border-color; border-top: 0; border-radius: 0 0 $border-radius-md $border-radius-md; overflow: hidden; background: $surface-color; }.conversation-panel { min-width: 0; min-height: 0; display: flex; flex-direction: column; background: $surface-color; }.workspace-camera { flex: 1; margin: 22px; }.message-list { min-height: 0; flex: 1; overflow-y: auto; padding: 28px max(22px, calc((100% - 840px) / 2)); }.empty-state { min-height: 100%; display: grid; align-content: center; justify-items: center; text-align: center; }.empty-mark { width: 58px; height: 58px; display: grid; place-items: center; border: 1px solid $border-color; border-radius: 50%; color: #fff; background: $primary-color; font-size: 25px; box-shadow: 0 16px 34px rgba(99, 102, 241, .24); }.empty-state h2 { margin: 16px 0 22px; font-family: 'Space Grotesk', 'DM Sans', sans-serif; font-size: 22px; }.starter-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; max-width: 680px; }.starter-grid button { padding: 14px; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; color: $text-regular; cursor: pointer; font-size: 12px; font-weight: 700; transition: border-color .2s, box-shadow .2s, transform .2s; }.starter-grid button:hover { border-color: $primary-color; color: $primary-color; background: $primary-soft; box-shadow: $ring-primary; transform: translateY(-1px); }
.new-chat-enter-active { transform-origin: center; transition: opacity .42s ease, transform .42s cubic-bezier(.22, 1, .36, 1), filter .42s ease; will-change: opacity, transform, filter; }
.new-chat-enter-from { opacity: 0; transform: translateY(14px) scale(.985); filter: blur(5px); }
.session-sidebar { min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: 14px 12px; border-right: 1px solid $border-color; background: $surface-muted; }.new-chat-button { width: 100%; }.session-heading { display: flex; align-items: center; justify-content: space-between; height: 38px; margin-top: 10px; padding-left: 5px; color: $text-secondary; font-size: 11px; font-weight: 800; }.session-list { min-height: 80px; flex: 1; overflow-y: auto; }.session-item { width: 100%; display: grid; grid-template-columns: 18px minmax(0, 1fr) 22px; align-items: center; gap: 8px; margin-bottom: 5px; padding: 9px 6px 9px 9px; border: 0; border-radius: $border-radius-sm; color: $text-secondary; background: transparent; text-align: left; cursor: pointer; transition: background .2s, color .2s; }.session-item:hover { background: #fff; }.session-item.active { color: $primary-color; background: $primary-soft; }.session-item > .el-icon { font-size: 15px; }.session-item > span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.session-item strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 700; }.session-item small { color: $text-placeholder; font-size: 9px; }.session-item .session-delete { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 5px; opacity: 0; color: $text-secondary; cursor: pointer; transition: color .2s, background .2s, opacity .2s; }.session-item:hover .session-delete, .session-item.active .session-delete { opacity: 1; }.session-item .session-delete:hover { color: $danger-color; background: rgba(239, 68, 68, .1); }.session-item .session-delete:focus-visible { opacity: 1; outline: 2px solid $primary-color; outline-offset: 2px; }.no-sessions { padding: 22px 4px; color: $text-placeholder; text-align: center; font-size: 11px; }
.message-row { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; margin-bottom: 24px; }.avatar { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; color: #fff; background: $primary-color; }.message-row.user .avatar { color: $text-primary; background: $surface-muted; }.message-label { margin-bottom: 6px; font-size: 11px; font-weight: 800; color: $text-secondary; }.message-content { color: $text-primary; line-height: 1.7; font-size: 14px; word-break: break-word; }.message-content :deep(p) { margin: 0 0 8px; }.message-files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }.message-files span { display: flex; align-items: center; gap: 5px; max-width: 240px; padding: 6px 9px; border: 1px solid $border-color; border-radius: $border-radius-sm; color: $text-secondary; background: $surface-muted; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.thinking { display: flex; gap: 5px; padding: 8px 0; }.thinking span { width: 7px; height: 7px; border-radius: 50%; background: $text-secondary; animation: pulse 1.1s infinite; }.thinking span:nth-child(2) { animation-delay: .15s; }.thinking span:nth-child(3) { animation-delay: .3s; }.tool-state { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; border-radius: $border-radius-sm; color: $warning-color; background: color-mix(in srgb, $warning-color 12%, $surface-color); font-size: 11px; font-weight: 700; }.stream-cursor { display: inline-block; width: 2px; height: 1em; margin-left: 3px; vertical-align: -2px; background: $primary-color; animation: cursor-blink .8s steps(1) infinite; }
.composer { padding: 14px max(22px, calc((100% - 840px) / 2)) 18px; border-top: 1px solid $border-color; background: $surface-color; }.composer-row { display: grid; grid-template-columns: 36px minmax(0, 1fr) 36px; align-items: end; gap: 9px; padding: 8px; border: 1px solid $border-color; border-radius: $border-radius-md; box-shadow: 0 10px 24px rgba(15, 23, 42, .06); }.composer-row:focus-within { border-color: $primary-color; box-shadow: $ring-primary; }.composer-row :deep(.el-textarea__inner) { min-height: 34px !important; padding: 7px 4px; border: 0; box-shadow: none; }.file-input { display: none; }.selected-files { display: flex; gap: 7px; overflow-x: auto; padding-bottom: 8px; }.selected-files > span { min-width: 0; max-width: 220px; height: 38px; display: grid; grid-template-columns: 28px minmax(0, 1fr) 22px; align-items: center; gap: 6px; padding: 4px 6px; border: 1px solid $border-color; border-radius: $border-radius-sm; background: $surface-muted; }.selected-files img { width: 28px; height: 28px; object-fit: cover; border-radius: 3px; }.selected-files b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }.selected-files button { border: 0; background: transparent; cursor: pointer; color: $text-secondary; }.send-button { align-self: end; }
.control-rail { overflow-y: auto; border-left: 1px solid $border-color; background: $surface-muted; }.rail-section { padding: 18px; border-bottom: 1px solid $border-color; }.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; font-size: 12px; font-weight: 800; color: $text-primary; }.section-title em { font-style: normal; font-size: 11px; color: $text-secondary; }.drop-zone { width: 100%; height: 112px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; border: 1px dashed $border-strong; border-radius: $border-radius-md; background: $surface-color; color: $text-secondary; cursor: pointer; transition: border-color .2s, background .2s, box-shadow .2s; }.drop-zone .el-icon { color: $primary-color; font-size: 26px; }.drop-zone strong { font-size: 12px; color: $text-primary; }.drop-zone span { font-size: 10px; color: $text-secondary; }.drop-zone:hover { border-color: $primary-color; background: $primary-soft; box-shadow: $ring-primary; }.input-modes { display: grid; grid-template-columns: repeat(5, 1fr); margin-top: 10px; border: 1px solid $border-color; border-radius: $border-radius-sm; overflow: hidden; }.input-modes button { height: 32px; border: 0; border-right: 1px solid $border-color; background: $surface-color; color: $text-secondary; font-size: 10px; cursor: pointer; font-weight: 700; }.input-modes button:last-child { border-right: 0; }.input-modes button:hover { color: $primary-color; background: $primary-soft; }.input-modes button.active { color: $primary-color; background: $primary-soft; font-weight: 800; }.parameters label { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 2px; color: $text-secondary; font-size: 11px; }.parameters label strong { color: $text-primary; }.parameters :deep(.el-input-number) { width: 100%; }.action-section { text-align: center; }.action-section .el-button { width: 100%; }.action-section > span { display: block; margin-top: 7px; color: $text-placeholder; font-size: 10px; }.summary-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: $border-color; border: 1px solid $border-color; border-radius: $border-radius-sm; overflow: hidden; }.summary-metrics div { padding: 12px; display: flex; flex-direction: column; background: $surface-color; }.summary-metrics strong { font-size: 21px; }.summary-metrics span { font-size: 10px; color: $text-secondary; }.summary-price { display: grid; grid-template-columns: 1fr auto; align-items: baseline; gap: 3px 8px; margin-top: 10px; padding: 10px; border-radius: $border-radius-sm; background: $surface-color; }.summary-price span { color: $text-secondary; font-size: 10px; }.summary-price strong { font-size: 17px; }.summary-price small { grid-column: 1 / -1; color: $warning-color; font-size: 9px; }.summary-section ul { list-style: none; padding: 0; margin: 10px 0 0; }.summary-section li { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid $border-color; font-size: 11px; }
.handoff-button { display: flex; margin-top: 12px; }
.confirmation-card { margin-top: 14px; padding: 14px; border: 1px solid color-mix(in srgb, $warning-color 40%, $border-color); border-radius: $border-radius-md; background: color-mix(in srgb, $warning-color 5%, $surface-color); }
.confirmation-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.confirmation-heading > div { display: flex; flex-direction: column; gap: 3px; }.confirmation-heading span { color: $warning-color; font-size: 10px; font-weight: 800; }.confirmation-heading strong { font-size: 14px; }.confirmation-card > p { margin: 10px 0; color: $text-secondary; font-size: 12px; line-height: 1.6; }.confirmation-card dl { display: grid; grid-template-columns: minmax(90px, .7fr) minmax(0, 1.3fr); margin: 10px 0; border: 1px solid $border-color; border-radius: $border-radius-sm; overflow: hidden; }.confirmation-card dt, .confirmation-card dd { margin: 0; padding: 7px 9px; border-bottom: 1px solid $border-color; font-size: 11px; }.confirmation-card dt { color: $text-secondary; background: $surface-muted; }.confirmation-card dd { overflow-wrap: anywhere; white-space: pre-wrap; }.confirmation-card dt:nth-last-of-type(1), .confirmation-card dd:nth-last-of-type(1) { border-bottom: 0; }.confirmation-card ul { margin: 9px 0; padding-left: 18px; color: $danger-color; font-size: 11px; line-height: 1.7; }.confirmation-actions { display: flex; gap: 8px; margin-top: 12px; }.confirmation-result { max-height: 180px; margin: 10px 0 0; padding: 9px; overflow: auto; border-radius: $border-radius-sm; background: $surface-muted; color: $text-secondary; font-size: 10px; white-space: pre-wrap; }.confirmation-card .confirmation-error { color: $danger-color; }
@keyframes pulse { 0%, 70%, 100% { opacity: .3; transform: translateY(0); } 35% { opacity: 1; transform: translateY(-2px); } }
@keyframes cursor-blink { 0%, 45% { opacity: 1; } 46%, 100% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .new-chat-enter-active { transition: none; } }

/* Apple-class visual hierarchy */
.workspace {
  gap: 16px;
  padding: 0;
  background: transparent;
}

.workspace-header {
  min-height: 104px;
  padding: 18px 28px;
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, .76);
  box-shadow: $shadow-sm;
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
}

.workspace-header h1 {
  margin: 5px 0 0;
  font-family: inherit;
  font-size: clamp(27px, 3vw, 34px);
  font-weight: 600;
  letter-spacing: -.035em;
}

.workspace-header p {
  margin: 6px 0 0;
  color: $text-secondary;
  font-size: 13px;
}

.kicker { font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.agent-status { font-weight: 500; }
.agent-status i { width: 6px; height: 6px; }
.agent-status.ready i { box-shadow: 0 0 0 4px rgba(36, 138, 61, .1); }

.workspace-grid {
  --session-column: 196px;
  --control-column: 288px;
  position: relative;
  grid-template-columns: var(--session-column) minmax(0, 1fr) var(--control-column);
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, .82);
  box-shadow: 0 16px 50px rgba(0, 0, 0, .05);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  transition: grid-template-columns .22s ease;
}
.workspace-grid.sessions-collapsed { --session-column: 0px; }
.workspace-grid.controls-collapsed { --control-column: 0px; }
.workspace-grid.sessions-collapsed .message-list,
.workspace-grid.controls-collapsed .message-list { padding-top: 96px; }
.workspace-grid.sessions-collapsed .workspace-camera,
.workspace-grid.controls-collapsed .workspace-camera { margin-top: 88px; }

.session-sidebar, .control-rail { background: rgba(245, 245, 247, .72); }
.session-sidebar { grid-column: 1; padding: 16px 12px; }
.conversation-panel { grid-column: 2; }
.control-rail { grid-column: 3; }
.session-toolbar { display: flex; align-items: center; gap: 8px; }
.new-chat-button { min-width: 44px; min-height: 44px; flex: 1; color: $text-primary; background: $surface-color; border-color: $border-color; box-shadow: none; }
.panel-toggle { width: 44px; min-width: 44px; height: 44px; color: $text-secondary; background: $surface-color; border-color: $border-color; }
.panel-toggle:hover { color: $primary-color; background: $surface-color; border-color: color-mix(in srgb, $primary-color 35%, $border-color); }
.panel-toggle:focus-visible { outline: 3px solid color-mix(in srgb, $primary-color 35%, transparent); outline-offset: 2px; }
.session-sidebar.collapsed { position: absolute; top: 0; left: 0; z-index: 10; width: 0; height: 0; min-height: 0; padding: 0; overflow: visible; background: transparent; border: 0; }
.session-sidebar.collapsed .session-toolbar { position: absolute; top: 12px; left: 12px; width: max-content; gap: 4px; padding: 4px; border: 1px solid $border-color; border-radius: 999px; background: $surface-muted; box-shadow: $shadow-md; }
.session-sidebar.collapsed .new-chat-button { width: 44px; flex: none; order: 2; }
.session-sidebar.collapsed .panel-toggle { order: 1; }
.session-sidebar.collapsed .new-chat-button,
.session-sidebar.collapsed .panel-toggle { color: $text-secondary; background: transparent; border-color: transparent; }
.session-sidebar.collapsed .new-chat-button:hover,
.session-sidebar.collapsed .panel-toggle:hover { color: $primary-color; background: $surface-color; }
.session-heading { margin-top: 14px; padding-inline: 8px; font-weight: 500; letter-spacing: .02em; }
.session-item { min-height: 46px; padding: 9px; border-radius: 10px; }
.session-item strong { font-size: 12px; font-weight: 500; }
.session-item small { font-size: 10px; }
.session-item.active { color: $text-primary; background: rgba(255, 255, 255, .94); box-shadow: $shadow-sm; }

.conversation-panel { background: rgba(255, 255, 255, .72); }
.message-list { padding-top: 36px; padding-bottom: 36px; }
.empty-state { padding: 48px 20px; }
.empty-mark {
  width: 64px;
  height: 64px;
  border: 0;
  border-radius: 18px;
  background: linear-gradient(145deg, #1688f8, #0068d4);
  box-shadow: 0 16px 38px rgba(0, 113, 227, .24), inset 0 1px rgba(255, 255, 255, .35);
}
.empty-mark img { width: 35px; height: 35px; }
.empty-eyebrow { margin-top: 18px; color: $primary-color; font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.empty-state h2 { margin: 7px 0 0; font-family: inherit; font-size: clamp(24px, 3vw, 32px); font-weight: 600; letter-spacing: -.03em; }
.empty-copy { max-width: 490px; margin: 10px 0 24px; color: $text-secondary; font-size: 14px; line-height: 1.6; }
.starter-grid { width: 100%; max-width: 590px; gap: 8px; }
.starter-grid button {
  min-height: 44px;
  padding: 11px 14px;
  color: $text-secondary;
  font-weight: 500;
  background: rgba(245, 245, 247, .72);
  border-radius: 999px;
}
.starter-grid button:hover { color: $text-primary; background: #fff; border-color: $border-strong; box-shadow: $shadow-sm; transform: translateY(-1px); }

.message-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 24px; }
.message-row.user { flex-direction: row-reverse; }
.message-body { min-width: 0; max-width: min(78%, 760px); }
.message-row.user .message-body { display: flex; flex-direction: column; align-items: flex-end; }
.avatar { flex: 0 0 34px; background: $primary-color; box-shadow: 0 4px 14px rgba(0, 113, 227, .16); }
.message-row.user .avatar { color: $primary-color; background: color-mix(in srgb, $primary-color 11%, $surface-color); box-shadow: none; }
.message-label { font-weight: 600; }
.message-row.user .message-label { text-align: right; }
.message-bubble { width: fit-content; max-width: 100%; padding: 12px 16px; color: $text-primary; background: $surface-muted; border: 1px solid $border-color; border-radius: 6px 18px 18px 18px; box-shadow: $shadow-sm; }
.message-row.user .message-bubble { color: #fff; background: $primary-color; border-color: transparent; border-radius: 18px 6px 18px 18px; box-shadow: 0 8px 22px rgba(0, 113, 227, .18); }
.message-content { font-size: 15px; line-height: 1.65; }
.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3),
.message-content :deep(h4),
.message-content :deep(strong) { color: $text-primary; }
.message-content :deep(a) { color: $primary-color; }
.message-content :deep(code) { padding: 2px 5px; color: $text-primary; background: $surface-muted; border: 1px solid $border-color; border-radius: 6px; }
.message-content :deep(pre) { margin: 10px 0; padding: 14px; overflow-x: auto; color: $text-primary; background: $surface-muted; border: 1px solid $border-color; border-radius: $border-radius-sm; }
.message-content :deep(pre code) { padding: 0; background: transparent; border: 0; }
.message-content :deep(blockquote) { margin: 10px 0; padding-left: 14px; color: $text-secondary; border-left: 3px solid $primary-color; }
.message-content :deep(th),
.message-content :deep(td) { padding: 7px 9px; color: $text-primary; border: 1px solid $border-color; }
.message-content :deep(p:last-child) { margin-bottom: 0; }
.message-row.user .message-content,
.message-row.user .message-content :deep(h1),
.message-row.user .message-content :deep(h2),
.message-row.user .message-content :deep(h3),
.message-row.user .message-content :deep(h4),
.message-row.user .message-content :deep(strong),
.message-row.user .message-content :deep(a) { color: #fff; }
.message-row.user .message-files span { color: #fff; background: rgba(255, 255, 255, .14); border-color: rgba(255, 255, 255, .28); }
.message-bubble .thinking { padding: 3px 0; }
.message-bubble .tool-state { margin-top: 8px; }

.composer { padding-top: 12px; background: rgba(255, 255, 255, .88); }
.composer-row {
  padding: 7px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .07);
}
.composer-row :deep(.el-textarea__inner) { font-size: 14px; }

.rail-section { padding: 20px; }
.control-rail { display: flex; flex-direction: column; overflow: hidden; }
.rail-toolbar { min-height: 60px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 12px 8px 20px; border-bottom: 1px solid $border-color; color: $text-primary; background: $surface-muted; font-size: 13px; font-weight: 600; }
.control-rail.collapsed { position: absolute; top: 0; right: 0; z-index: 10; width: 0; height: 0; min-height: 0; padding: 0; overflow: visible; background: transparent; border: 0; }
.control-rail.collapsed .rail-toolbar { position: absolute; top: 12px; right: 12px; width: 52px; min-height: 52px; justify-content: center; padding: 4px; border: 1px solid $border-color; border-radius: 999px; background: $surface-muted; box-shadow: $shadow-md; }
.control-rail.collapsed .panel-toggle { color: $text-secondary; background: transparent; border-color: transparent; }
.control-rail.collapsed .panel-toggle:hover { color: $primary-color; background: $surface-color; }
.control-rail-body { min-height: 0; flex: 1; overflow-y: auto; }
.section-title { font-size: 13px; font-weight: 600; }
.drop-zone {
  height: 128px;
  gap: 7px;
  border-color: color-mix(in srgb, $primary-color 30%, $border-color);
  border-radius: 16px;
  background: $surface-color;
}
.drop-zone .el-icon { font-size: 28px; }
.drop-zone strong { font-size: 13px; font-weight: 600; }
.drop-zone span { font-size: 11px; }
.drop-zone:hover {
  color: $text-primary;
  background: color-mix(in srgb, $primary-color 10%, $surface-color);
  border-color: $primary-color;
  box-shadow: $ring-primary;
}
.input-modes { gap: 4px; padding: 4px; border: 0; border-radius: 12px; background: rgba(0, 0, 0, .045); }
.input-modes button { height: 34px; border: 0; border-radius: 9px; background: transparent; font-weight: 500; }
.input-modes button.active { color: $text-primary; background: #fff; box-shadow: 0 1px 5px rgba(0, 0, 0, .08); }
.parameters label { font-size: 12px; }
.action-section .el-button { min-height: 46px; }
.action-section > span { margin-top: 9px; font-size: 11px; }

@media (max-width: 1180px) {
  .workspace-grid { --session-column: 170px; --control-column: 250px; }
  .workspace-grid.sessions-collapsed { --session-column: 0px; }
  .workspace-grid.controls-collapsed { --control-column: 0px; }
  .rail-section { padding: 14px; }
}
@media (max-width: 980px) {
  .workspace-grid { grid-template-columns: 1fr; transition: none; }
  .session-sidebar, .conversation-panel, .control-rail { grid-column: 1; }
  .session-sidebar { min-height: 150px; max-height: 190px; border-right: 0; border-bottom: 1px solid $border-color; }
  .session-sidebar.collapsed { min-height: 0; max-height: 0; }
  .session-list { display: flex; gap: 6px; overflow-x: auto; }
  .session-item { min-width: 170px; max-width: 210px; }
  .control-rail { max-height: 360px; border-left: 0; border-top: 1px solid $border-color; }
  .control-rail.collapsed { min-height: 0; max-height: 0; }
  .control-rail-body { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .conversation-panel { min-height: 620px; }
  .summary-section { display: none; }
}
@media (max-width: 640px) {
  .workspace { min-height: 100%; }
  .workspace-header { padding: 10px 12px; }
  .workspace-header h1 { font-size: 17px; }
  .agent-status { display: none; }
  .message-list, .composer { padding-left: 12px; padding-right: 12px; }
  .message-body { max-width: calc(100% - 46px); }
  .message-bubble { padding: 10px 13px; }
  .starter-grid { grid-template-columns: 1fr; width: 100%; }
  .control-rail { max-height: none; }
  .control-rail-body { grid-template-columns: 1fr; }
  .parameters { display: none; }
  .conversation-panel { min-height: 560px; }
}

@media (prefers-reduced-motion: reduce) {
  .workspace-grid { transition: none; }
}
</style>
