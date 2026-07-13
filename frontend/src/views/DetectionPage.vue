<template>
  <div class="workspace" @dragover.prevent @drop.prevent="handleDrop">
    <header class="workspace-header">
      <div>
        <span class="kicker">VISIONPAY / RETAIL VISION</span>
        <h1>商品检测工作台</h1>
      </div>
      <div class="header-actions">
        <span :class="['agent-status', { ready: agentStatus.configured }]">
          <i></i>{{ agentStatus.configured ? agentStatus.model : 'Agent 未配置' }}
        </span>
        <el-tooltip content="创建新对话" placement="bottom">
          <el-button :icon="Plus" circle @click="resetWorkspace" />
        </el-tooltip>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="session-sidebar">
        <el-button class="new-chat-button" type="primary" :icon="Plus" @click="createNewChat">
          新对话
        </el-button>
        <div class="session-heading">
          <span>历史对话</span>
          <el-tooltip content="刷新历史">
            <el-button text :icon="Refresh" :loading="sessionLoading" @click="loadSessions" />
          </el-tooltip>
        </div>
        <div class="session-list" v-loading="sessionLoading">
          <button
            v-for="session in agentStore.sessions"
            :key="session.session_uuid"
            type="button"
            :class="['session-item', { active: session.session_uuid === agentStore.currentSessionId }]"
            @click="openSession(session.session_uuid)"
          >
            <el-icon><ChatLineSquare /></el-icon>
            <span><strong>{{ session.title }}</strong><small>{{ formatSessionTime(session.last_message_at || session.created_at) }}</small></span>
            <el-tooltip content="删除对话" placement="right">
              <i role="button" tabindex="0" @click.stop="removeSession(session)" @keydown.enter.stop="removeSession(session)"><el-icon><Delete /></el-icon></i>
            </el-tooltip>
          </button>
          <div v-if="!sessionLoading && !agentStore.sessions.length" class="no-sessions">暂无历史对话</div>
        </div>
      </aside>

      <main class="conversation-panel">
        <div ref="messageListRef" class="message-list">
          <section v-if="!agentStore.messages.length" class="empty-state">
            <div class="empty-mark"><el-icon><View /></el-icon></div>
            <h2>商品识别 Agent</h2>
            <div class="starter-grid">
              <button type="button" @click="inputText = '识别附件中的商品，并按类别汇总数量'">识别并汇总商品</button>
              <button type="button" @click="inputText = '检查识别结果中置信度较低的商品'">定位低置信度结果</button>
              <button type="button" @click="inputText = '根据识别结果生成结算商品清单'">生成结算清单</button>
            </div>
          </section>

          <article v-for="(message, index) in agentStore.messages" :key="index" :class="['message-row', message.role]">
            <div class="avatar"><el-icon><User v-if="message.role === 'user'" /><Cpu v-else /></el-icon></div>
            <div class="message-body">
              <div class="message-label">{{ message.role === 'user' ? '你' : 'VisionPay Agent' }}</div>
              <div v-if="message.content" class="message-content" v-html="message.role === 'assistant' ? renderMarkdown(message.content) : escapeText(message.content)"></div>
              <div v-if="message.files?.length" class="message-files">
                <span v-for="file in message.files" :key="file.name"><el-icon><Document /></el-icon>{{ file.name }}</span>
              </div>
              <div v-if="message.loading && !message.content" class="thinking"><span></span><span></span><span></span></div>
              <div v-if="message.tool" class="tool-state"><el-icon><Operation /></el-icon>{{ toolName(message.tool) }} 正在处理</div>
              <DetectionResultCard v-if="message.result" :result="message.result" />
            </div>
          </article>
        </div>

        <footer class="composer">
          <div v-if="selectedFiles.length" class="selected-files">
            <span v-for="(item, index) in selectedFiles" :key="item.id">
              <img v-if="item.preview" :src="item.preview" alt="" />
              <el-icon v-else><FolderOpened /></el-icon>
              <b :title="item.file.name">{{ item.file.name }}</b>
              <button type="button" aria-label="移除附件" @click="removeFile(index)"><el-icon><Close /></el-icon></button>
            </span>
          </div>
          <div class="composer-row">
            <input ref="singleInputRef" class="file-input" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" @change="handleFileInput($event, 'single')" />
            <input ref="batchInputRef" class="file-input" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" multiple @change="handleFileInput($event, 'batch')" />
            <input ref="zipInputRef" class="file-input" type="file" accept=".zip,application/zip" @change="handleFileInput($event, 'zip')" />
            <el-tooltip content="按当前模式添加文件" placement="top"><el-button :icon="Paperclip" circle :disabled="busy" @click="openModePicker(inputMode)" /></el-tooltip>
            <el-input v-model="inputText" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" resize="none" placeholder="向识别 Agent 发出指令" :disabled="busy" @keydown.enter.exact.prevent="sendToAgent" />
            <el-tooltip :content="busy ? '停止响应' : '发送给 Agent'" placement="top">
              <el-button class="send-button" :type="busy ? 'danger' : 'primary'" :icon="busy ? VideoPause : Promotion" circle :disabled="!busy && !canSend" @click="busy ? stopStream() : sendToAgent()" />
            </el-tooltip>
          </div>
        </footer>
      </main>

      <aside class="control-rail">
        <section class="rail-section">
          <div class="section-title"><span>检测输入</span><em>{{ selectedFiles.length }}</em></div>
          <button class="drop-zone" type="button" :disabled="busy" @click="openModePicker(inputMode)">
            <el-icon><UploadFilled /></el-icon><strong>{{ modeCopy.title }}</strong><span>{{ modeCopy.hint }}</span>
          </button>
          <div class="input-modes">
            <button type="button" :class="{ active: inputMode === 'single' }" @click="selectMode('single')"><el-icon><Picture /></el-icon>单图</button>
            <button type="button" :class="{ active: inputMode === 'batch' }" @click="selectMode('batch')"><el-icon><Files /></el-icon>多图</button>
            <button type="button" :class="{ active: inputMode === 'zip' }" @click="selectMode('zip')"><el-icon><Folder /></el-icon>ZIP</button>
          </div>
        </section>

        <section class="rail-section parameters">
          <div class="section-title"><span>推理参数</span></div>
          <label>置信度 <strong>{{ Math.round(confidence * 100) }}%</strong></label>
          <el-slider v-model="confidence" :min="0.05" :max="0.95" :step="0.05" :show-tooltip="false" />
          <label>NMS IoU <strong>{{ Math.round(iou * 100) }}%</strong></label>
          <el-slider v-model="iou" :min="0.05" :max="0.95" :step="0.05" :show-tooltip="false" />
          <label>场景 ID <el-tooltip content="留空时使用首个可用场景"><el-icon><QuestionFilled /></el-icon></el-tooltip></label>
          <el-input-number v-model="sceneId" :min="1" :controls="false" placeholder="自动" />
        </section>

        <section class="rail-section action-section">
          <el-button type="primary" :icon="Aim" :loading="directLoading" :disabled="!selectedFiles.length || agentStore.isLoading" @click="runDirectDetection">立即识别</el-button>
          <span>直接调用 YOLO 推理</span>
        </section>

        <section v-if="latestResult" class="rail-section summary-section">
          <div class="section-title"><span>本次汇总</span><em>#{{ latestResult.task_id }}</em></div>
          <div class="summary-metrics"><div><strong>{{ latestResult.total_objects }}</strong><span>商品</span></div><div><strong>{{ latestResult.total_images }}</strong><span>图片</span></div></div>
          <ul><li v-for="(count, name) in latestResult.class_counts" :key="name"><span>{{ name }}</span><strong>{{ count }}</strong></li></ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Aim, ChatLineSquare, Close, Cpu, Delete, Document, Files, Folder, FolderOpened, Operation, Paperclip, Picture, Plus, Promotion, QuestionFilled, Refresh, UploadFilled, User, VideoPause, View } from '@element-plus/icons-vue'
import DetectionResultCard from '@/components/DetectionResultCard.vue'
import { createDetectionSessionApi, deleteDetectionSessionApi, detectBatchApi, detectSingleApi, detectZipApi, getAgentStatusApi, getDetectionSessionApi, getDetectionSessionsApi, saveDetectionExchangeApi, uploadChatFilesApi } from '@/api/detection'
import { useAgentStore } from '@/stores/agent'
import { renderMarkdown } from '@/utils/markdown'
import { streamChat } from '@/utils/stream'

const agentStore = useAgentStore()
const inputText = ref('')
const selectedFiles = ref([])
const confidence = ref(0.25)
const iou = ref(0.45)
const sceneId = ref(undefined)
const directLoading = ref(false)
const singleInputRef = ref(null)
const batchInputRef = ref(null)
const zipInputRef = ref(null)
const messageListRef = ref(null)
const agentStatus = ref({ configured: false, model: 'DeepSeek' })
const latestResult = ref(null)
const inputMode = ref('single')
const sessionLoading = ref(false)
const busy = computed(() => directLoading.value || agentStore.isLoading)
const canSend = computed(() => inputText.value.trim() || selectedFiles.value.length)
const modeCopy = computed(() => ({
  single: { title: '选择一张商品图片', hint: 'JPG / PNG / BMP / WEBP' },
  batch: { title: '选择多张商品图片', hint: '最多 30 张图片' },
  zip: { title: '选择一个 ZIP 文件', hint: 'ZIP 内最多 30 张图片' },
})[inputMode.value])

onMounted(async () => {
  try { agentStatus.value = await getAgentStatusApi() } catch { /* auth interceptor reports errors */ }
  await loadSessions()
  if (agentStore.currentSessionId && agentStore.sessions.some((item) => item.session_uuid === agentStore.currentSessionId)) {
    await openSession(agentStore.currentSessionId)
  } else if (agentStore.sessions.length) {
    await openSession(agentStore.sessions[0].session_uuid)
  } else {
    await createNewChat()
  }
})
onBeforeUnmount(() => { stopStream(); clearSelectedFiles() })
function escapeText(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML.replace(/\n/g, '<br>') }
function toolName(name) { return ({ detect_single_product_image: '单图商品识别', detect_product_images: '批量商品识别', detect_product_zip: 'ZIP 商品识别' })[name] || name }
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
  agentStore.sessions.unshift(session)
  return session.session_uuid
}
async function createNewChat() {
  stopStream()
  const session = await createDetectionSessionApi()
  agentStore.currentSessionId = session.session_uuid
  agentStore.messages = []
  agentStore.sessions = [session, ...agentStore.sessions.filter((item) => item.session_uuid !== session.session_uuid)]
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
      else await createNewChat()
    }
  } catch (error) { if (error !== 'cancel' && error !== 'close') throw error }
}
function formatSessionTime(value) {
  if (!value) return ''
  const date = new Date(value)
  const today = new Date()
  return date.toDateString() === today.toDateString() ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
function selectMode(mode) {
  if (busy.value) return
  inputMode.value = mode
  clearSelectedFiles()
  openModePicker(mode)
}
function openModePicker(mode) {
  const refs = { single: singleInputRef, batch: batchInputRef, zip: zipInputRef }
  refs[mode]?.value?.click()
}
function selectFiles(files, mode = inputMode.value) {
  const expression = mode === 'zip' ? /\.zip$/i : /\.(jpe?g|png|bmp|webp)$/i
  const incoming = [...files].filter((file) => expression.test(file.name))
  const next = mode === 'batch' ? incoming.slice(0, 30) : incoming.slice(0, 1)
  clearSelectedFiles()
  selectedFiles.value = next.map((file) => ({ id: `${file.name}-${file.lastModified}`, file, preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : '' }))
  if (files.length && !incoming.length) ElMessage.warning(mode === 'zip' ? '请选择 ZIP 文件' : '请选择商品图片')
}
function handleFileInput(event, mode) { inputMode.value = mode; selectFiles(event.target.files, mode); event.target.value = '' }
function handleDrop(event) {
  if (busy.value) return
  const files = [...event.dataTransfer.files]
  const mode = files.some((file) => /\.zip$/i.test(file.name)) ? 'zip' : files.length > 1 ? 'batch' : 'single'
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
  const userContent = '立即识别所选商品图片'
  agentStore.addMessage({ role: 'user', content: userContent, files: fileMetadata })
  const assistant = { role: 'assistant', content: '', loading: true, tool: 'yolo_direct', result: null }
  agentStore.addMessage(assistant); scrollBottom()
  try {
    const result = inputMode.value === 'zip' ? await detectZipApi(files[0], options()) : inputMode.value === 'single' ? await detectSingleApi(files[0], options()) : await detectBatchApi(files, options())
    assistant.content = `识别完成，共处理 ${result.total_images} 张图片，发现 ${result.total_objects} 件商品。`
    assistant.result = result; assistant.tool = ''; latestResult.value = result; clearSelectedFiles()
    await saveDetectionExchangeApi(sessionUuid, { user_content: userContent, assistant_content: assistant.content, files: fileMetadata, result })
    await loadSessions()
  } catch { assistant.content = '识别任务未完成，请检查模型、场景与后端日志。'; assistant.tool = '' }
  finally { assistant.loading = false; directLoading.value = false; scrollBottom() }
}

async function sendToAgent() {
  if (!canSend.value || busy.value) return
  const sessionUuid = await ensureSession()
  const text = inputText.value.trim() || '识别附件中的商品并汇总数量'
  const files = selectedFiles.value.map((item) => item.file)
  agentStore.addMessage({ role: 'user', content: text, files: files.map((file) => ({ name: file.name })) })
  const assistant = { role: 'assistant', content: '', loading: true, tool: '', result: null }
  agentStore.addMessage(assistant); inputText.value = ''; agentStore.setLoading(true); scrollBottom()
  try {
    const upload = files.length ? await uploadChatFilesApi(files) : { files: [] }
    const stream = streamChat('/api/chat/stream', { message: text, attachment_paths: upload.files.map((file) => file.path), attachment_names: files.map((file) => ({ name: file.name })), scene_id: sceneId.value, session_uuid: sessionUuid }, {
      onMessage(event) {
        if (event.type === 'text_chunk') assistant.content += event.content
        if (event.type === 'tool_call') assistant.tool = event.tool
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
function resetWorkspace() { createNewChat() }
</script>

<style lang="scss" scoped>
.workspace { height: 100%; min-height: 620px; display: flex; flex-direction: column; color: #1c2835; background: #f3f5f7; }
.workspace-header { min-height: 68px; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #dce2e8; background: #fff; }.workspace-header h1 { margin: 2px 0 0; font-size: 20px; line-height: 1.2; letter-spacing: 0; }.kicker { font-size: 10px; color: #7b8794; letter-spacing: 0; }.header-actions { display: flex; align-items: center; gap: 10px; }.agent-status { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #8a5360; }.agent-status i { width: 7px; height: 7px; border-radius: 50%; background: #d76575; }.agent-status.ready { color: #26775b; }.agent-status.ready i { background: #28a273; box-shadow: 0 0 0 3px #dff3eb; }
.workspace-grid { min-height: 0; flex: 1; display: grid; grid-template-columns: 190px minmax(0, 1fr) 280px; }.conversation-panel { min-width: 0; min-height: 0; display: flex; flex-direction: column; background: #fff; }.message-list { min-height: 0; flex: 1; overflow-y: auto; padding: 24px max(20px, calc((100% - 840px) / 2)); }.empty-state { min-height: 100%; display: grid; align-content: center; justify-items: center; text-align: center; }.empty-mark { width: 54px; height: 54px; display: grid; place-items: center; border: 1px solid #cdd7e1; border-radius: 8px; color: #1677ff; background: #f6f9fc; font-size: 25px; }.empty-state h2 { margin: 14px 0 20px; font-size: 18px; }.starter-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 650px; }.starter-grid button { padding: 12px; border: 1px solid #dce2e8; border-radius: 6px; background: #fff; color: #4b5968; cursor: pointer; font-size: 12px; }.starter-grid button:hover { border-color: #1677ff; color: #1266dc; background: #f7faff; }
.session-sidebar { min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: 12px 10px; border-right: 1px solid #dce2e8; background: #f7f9fb; }.new-chat-button { width: 100%; }.session-heading { display: flex; align-items: center; justify-content: space-between; height: 38px; margin-top: 10px; padding-left: 5px; color: #718090; font-size: 11px; font-weight: 700; }.session-list { min-height: 80px; flex: 1; overflow-y: auto; }.session-item { width: 100%; display: grid; grid-template-columns: 18px minmax(0, 1fr) 22px; align-items: center; gap: 7px; margin-bottom: 3px; padding: 8px 5px 8px 8px; border: 0; border-radius: 5px; color: #526171; background: transparent; text-align: left; cursor: pointer; }.session-item:hover { background: #edf2f7; }.session-item.active { color: #1267db; background: #e7f1ff; }.session-item > span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.session-item strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 600; }.session-item small { color: #8c97a2; font-size: 9px; }.session-item i { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 3px; opacity: 0; color: #7c8792; cursor: pointer; }.session-item:hover i, .session-item.active i { opacity: 1; }.session-item i:hover { color: #d64b5d; background: #fff; }.no-sessions { padding: 22px 4px; color: #9aa4ae; text-align: center; font-size: 11px; }
.message-row { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 11px; margin-bottom: 24px; }.avatar { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 5px; color: #fff; background: #263849; }.message-row.user .avatar { color: #354251; background: #edf1f5; }.message-label { margin-bottom: 6px; font-size: 11px; font-weight: 700; color: #6d7885; }.message-content { line-height: 1.7; font-size: 14px; word-break: break-word; }.message-content :deep(p) { margin: 0 0 8px; }.message-files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }.message-files span { display: flex; align-items: center; gap: 5px; max-width: 240px; padding: 5px 8px; border: 1px solid #dde4eb; border-radius: 4px; color: #536170; background: #f8fafb; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.thinking { display: flex; gap: 4px; padding: 7px 0; }.thinking span { width: 6px; height: 6px; border-radius: 50%; background: #8794a1; animation: pulse 1.1s infinite; }.thinking span:nth-child(2) { animation-delay: .15s; }.thinking span:nth-child(3) { animation-delay: .3s; }.tool-state { display: inline-flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; color: #86600d; background: #fff6db; font-size: 11px; }
.composer { padding: 12px max(20px, calc((100% - 840px) / 2)) 16px; border-top: 1px solid #e3e7eb; background: #fff; }.composer-row { display: grid; grid-template-columns: 34px minmax(0, 1fr) 34px; align-items: end; gap: 8px; padding: 7px; border: 1px solid #cfd7df; border-radius: 8px; box-shadow: 0 5px 18px rgba(36, 54, 73, .06); }.composer-row:focus-within { border-color: #1677ff; box-shadow: 0 0 0 2px rgba(22,119,255,.08); }.composer-row :deep(.el-textarea__inner) { min-height: 32px !important; padding: 6px 4px; border: 0; box-shadow: none; }.file-input { display: none; }.selected-files { display: flex; gap: 7px; overflow-x: auto; padding-bottom: 8px; }.selected-files > span { min-width: 0; max-width: 220px; height: 36px; display: grid; grid-template-columns: 28px minmax(0, 1fr) 22px; align-items: center; gap: 6px; padding: 3px 5px; border: 1px solid #dce3e9; border-radius: 5px; background: #f8fafc; }.selected-files img { width: 28px; height: 28px; object-fit: cover; border-radius: 3px; }.selected-files b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }.selected-files button { border: 0; background: transparent; cursor: pointer; color: #75808c; }.send-button { align-self: end; }
.control-rail { overflow-y: auto; border-left: 1px solid #dce2e8; background: #f7f9fa; }.rail-section { padding: 18px; border-bottom: 1px solid #dfe4e9; }.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; font-size: 12px; font-weight: 700; color: #344251; }.section-title em { font-style: normal; font-size: 11px; color: #697788; }.drop-zone { width: 100%; height: 106px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; border: 1px dashed #aebbc8; border-radius: 6px; background: #fff; color: #586777; cursor: pointer; }.drop-zone .el-icon { color: #1677ff; font-size: 25px; }.drop-zone strong { font-size: 12px; }.drop-zone span { font-size: 10px; color: #8b96a2; }.drop-zone:hover { border-color: #1677ff; background: #f7faff; }.input-modes { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 10px; border: 1px solid #d5dde5; border-radius: 5px; overflow: hidden; }.input-modes button { height: 31px; border: 0; border-right: 1px solid #d5dde5; background: #fff; color: #6b7886; font-size: 11px; cursor: pointer; }.input-modes button:last-child { border-right: 0; }.input-modes button:hover { color: #1267db; background: #f4f8fd; }.input-modes button.active { color: #1267db; background: #eaf3ff; font-weight: 700; }.parameters label { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 2px; color: #596878; font-size: 11px; }.parameters label strong { color: #263544; }.parameters :deep(.el-input-number) { width: 100%; }.action-section { text-align: center; }.action-section .el-button { width: 100%; }.action-section > span { display: block; margin-top: 7px; color: #89939d; font-size: 10px; }.summary-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #dce2e8; border: 1px solid #dce2e8; }.summary-metrics div { padding: 12px; display: flex; flex-direction: column; background: #fff; }.summary-metrics strong { font-size: 21px; }.summary-metrics span { font-size: 10px; color: #7a8794; }.summary-section ul { list-style: none; padding: 0; margin: 10px 0 0; }.summary-section li { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #e5e9ed; font-size: 11px; }
@keyframes pulse { 0%, 70%, 100% { opacity: .3; transform: translateY(0); } 35% { opacity: 1; transform: translateY(-2px); } }
@media (max-width: 1180px) { .workspace-grid { grid-template-columns: 170px minmax(0, 1fr) 250px; }.rail-section { padding: 14px; } }
@media (max-width: 980px) { .workspace-grid { grid-template-columns: 1fr; }.session-sidebar { min-height: 150px; max-height: 190px; border-right: 0; border-bottom: 1px solid #dce2e8; }.session-list { display: flex; gap: 6px; overflow-x: auto; }.session-item { min-width: 170px; max-width: 210px; }.control-rail { display: grid; grid-template-columns: repeat(2, 1fr); border-left: 0; border-top: 1px solid #dce2e8; max-height: 300px; }.conversation-panel { min-height: 620px; }.summary-section { display: none; } }
@media (max-width: 640px) { .workspace { min-height: 100%; }.workspace-header { padding: 10px 12px; }.workspace-header h1 { font-size: 17px; }.agent-status { display: none; }.message-list, .composer { padding-left: 12px; padding-right: 12px; }.starter-grid { grid-template-columns: 1fr; width: 100%; }.control-rail { grid-template-columns: 1fr; max-height: none; }.parameters { display: none; }.conversation-panel { min-height: 560px; } }
</style>
