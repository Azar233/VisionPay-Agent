<template>
  <section :class="['ip-camera-panel', { compact }]">
    <header class="camera-head">
      <div>
        <i :class="{ live: running }"></i>
        <span>{{ statusText }}</span>
      </div>
      <small>IP WEBCAM · YOLO · CPU</small>
    </header>

    <div class="camera-screen">
      <canvas ref="canvasRef"></canvas>
      <div v-if="!hasFrame" class="camera-empty">
        <el-icon><VideoCamera /></el-icon>
        <strong>{{ loading ? '正在连接并预热模型' : '实时检测尚未启动' }}</strong>
        <span>手机与电脑需连接同一 Wi-Fi，并在手机端启动 IP Webcam 服务器</span>
      </div>
      <div v-if="running" class="live-badge">LIVE</div>
    </div>

    <div class="camera-metrics">
      <div><span>当前商品</span><strong>{{ result.object_count || 0 }}</strong></div>
      <div><span>处理帧率</span><strong>{{ Number(result.fps || 0).toFixed(1) }} FPS</strong></div>
      <div><span>推理耗时</span><strong>{{ Number(result.inference_time_ms || 0).toFixed(0) }} ms</strong></div>
      <div><span>已处理</span><strong>{{ result.frame_count || 0 }} 帧</strong></div>
    </div>

    <div v-if="classes.length" class="camera-classes">
      <span v-for="item in classes" :key="item.name">{{ item.name }} <b>{{ item.count }}</b></span>
    </div>
    <p v-if="error" class="camera-error">{{ error }}</p>

    <footer class="camera-actions">
      <div>
        <span>{{ modelInfo }}</span>
        <small>416 × 416 · 目标 3 FPS · 当前帧计数</small>
      </div>
      <el-button v-if="!active" type="primary" :loading="loading" @click="start">开始实时检测</el-button>
      <el-button v-else type="danger" plain @click="stop">停止检测</el-button>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { VideoCamera } from '@element-plus/icons-vue'

const props = defineProps({
  sceneId: { type: Number, default: undefined },
  conf: { type: Number, default: 0.25 },
  iou: { type: Number, default: 0.45 },
  autoStart: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['result', 'status'])

const canvasRef = ref(null)
const active = ref(false)
const running = ref(false)
const loading = ref(false)
const hasFrame = ref(false)
const error = ref('')
const statusText = ref('等待启动')
const modelInfo = ref('模型将在连接后加载')
const result = ref({})
let socket = null
let intentionalClose = false
let reconnectAttempts = 0
let reconnectTimer = null

const classes = computed(() => Object.entries(result.value.class_counts || {}).map(([name, count]) => ({ name, count })))

function socketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/detection/camera`
}

function setStatus(value) {
  statusText.value = value
  emit('status', { active: active.value, running: running.value, loading: loading.value, error: error.value, text: value })
}

async function renderFrame(base64) {
  const canvas = canvasRef.value
  if (!canvas || !base64) return
  const image = new Image()
  image.onload = () => {
    canvas.width = image.naturalWidth
    canvas.height = image.naturalHeight
    canvas.getContext('2d')?.drawImage(image, 0, 0)
    hasFrame.value = true
  }
  image.src = `data:image/jpeg;base64,${base64}`
}

function connect() {
  window.clearTimeout(reconnectTimer)
  error.value = ''
  loading.value = true
  active.value = true
  running.value = false
  intentionalClose = false
  setStatus('正在连接')
  socket = new WebSocket(socketUrl())
  socket.onopen = () => {
    setStatus('正在加载模型')
    socket.send(JSON.stringify({
      type: 'config',
      mode: 'cpu',
      conf: props.conf,
      iou: props.iou,
      scene_id: props.sceneId || null,
    }))
  }
  socket.onmessage = async (event) => {
    const message = JSON.parse(event.data)
    if (message.type === 'config_ok') {
      reconnectAttempts = 0
      loading.value = false
      running.value = true
      modelInfo.value = `${message.model} · ${message.scene}`
      setStatus('实时识别中')
      return
    }
    if (message.type === 'result') {
      result.value = message
      await nextTick()
      renderFrame(message.annotated_frame)
      emit('result', message)
      return
    }
    if (message.type === 'error') {
      error.value = message.message || '实时检测失败'
      loading.value = false
      running.value = false
      setStatus('检测异常')
    }
  }
  socket.onerror = () => {
    error.value = '无法建立实时检测连接，请确认后端和 IP Webcam 已启动'
  }
  socket.onclose = () => {
    socket = null
    running.value = false
    loading.value = false
    if (intentionalClose || !active.value) {
      active.value = false
      setStatus('已停止')
      return
    }
    if (reconnectAttempts < 3) {
      const delay = 800 * (2 ** reconnectAttempts)
      reconnectAttempts += 1
      setStatus(`连接中断，${reconnectAttempts}/3 次重连`)
      reconnectTimer = window.setTimeout(connect, delay)
    } else {
      active.value = false
      error.value ||= '实时检测连接已断开，请手动重试'
      setStatus('连接失败')
    }
  }
}

function start() {
  if (active.value) return
  reconnectAttempts = 0
  connect()
}

function stop() {
  intentionalClose = true
  active.value = false
  running.value = false
  loading.value = false
  window.clearTimeout(reconnectTimer)
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'close' }))
  socket?.close()
  socket = null
  setStatus('已停止')
}

onMounted(() => { if (props.autoStart) start() })
onBeforeUnmount(stop)
defineExpose({ start, stop })
</script>

<style lang="scss" scoped>
.ip-camera-panel { overflow: hidden; border: 1px solid $border-color; border-radius: $border-radius-md; background: $surface-color; box-shadow: $shadow-sm; }
.camera-head { height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; color: #dfe7ec; background: #1e2a34; font-size: 11px; }.camera-head > div { display: flex; align-items: center; gap: 7px; }.camera-head i { width: 7px; height: 7px; border-radius: 50%; background: #71808c; }.camera-head i.live { background: #2bd88f; box-shadow: 0 0 0 4px rgba(43,216,143,.13); }.camera-head small { color: #8fa0ad; }
.camera-screen { position: relative; min-height: 360px; display: grid; place-items: center; overflow: hidden; background: #101820; }.camera-screen canvas { display: block; width: 100%; height: 100%; max-height: 58vh; object-fit: contain; }.camera-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 24px; color: #aebbc5; text-align: center; }.camera-empty .el-icon { font-size: 44px; color: #657682; }.camera-empty strong { color: #d8e1e7; }.camera-empty span { max-width: 430px; font-size: 11px; line-height: 1.6; }.live-badge { position: absolute; top: 12px; left: 12px; padding: 4px 7px; border-radius: 3px; color: #fff; background: #dc2626; font-size: 9px; font-weight: 900; letter-spacing: .08em; }
.camera-metrics { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid $border-color; border-bottom: 1px solid $border-color; }.camera-metrics > div { padding: 11px 13px; display: flex; flex-direction: column; gap: 3px; border-right: 1px solid $border-color; }.camera-metrics > div:last-child { border-right: 0; }.camera-metrics span { color: $text-secondary; font-size: 9px; }.camera-metrics strong { color: $text-primary; font-size: 13px; }
.camera-classes { display: flex; gap: 6px; padding: 9px 12px; overflow-x: auto; background: $surface-muted; }.camera-classes span { flex-shrink: 0; padding: 5px 8px; border: 1px solid $border-color; border-radius: 4px; background: $surface-color; color: $text-secondary; font-size: 10px; }.camera-classes b { margin-left: 4px; color: $text-primary; }.camera-error { margin: 0; padding: 9px 13px; color: #9c2938; background: #fff0f2; font-size: 11px; }
.camera-actions { min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 12px; }.camera-actions > div { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.camera-actions span { overflow: hidden; color: $text-primary; font-size: 11px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }.camera-actions small { color: $text-secondary; font-size: 9px; }
.compact { border-radius: 0; box-shadow: none; }.compact .camera-screen { min-height: 340px; }.compact .camera-actions { border-top: 1px solid $border-color; }
@media (max-width: 640px) { .camera-screen, .compact .camera-screen { min-height: 260px; }.camera-metrics { grid-template-columns: repeat(2, 1fr); }.camera-metrics > div:nth-child(2) { border-right: 0; }.camera-metrics > div:nth-child(-n+2) { border-bottom: 1px solid $border-color; } }
</style>
