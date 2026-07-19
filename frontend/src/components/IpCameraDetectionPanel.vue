<template>
  <section :class="['ip-camera-panel', { compact }]">
    <header class="camera-head">
      <div>
        <i :class="{ live: running }"></i>
        <span>{{ statusText }}</span>
      </div>
      <small>IP WEBCAM · YOLO · CPU</small>
    </header>

    <div class="camera-address">
      <label for="ip-webcam-url">手机摄像头地址</label>
      <el-input
        id="ip-webcam-url"
        v-model.trim="cameraUrl"
        :disabled="active"
        placeholder="http://10.172.52.70:8080"
        clearable
        @change="saveCameraUrl"
      />
      <button type="button" class="mode-toggle" :disabled="active" @click="accumulate = !accumulate">
        <span>{{ accumulate ? '累计模式' : '瞬时模式' }}</span>
        <span :class="['mode-switch', { active: accumulate }]" aria-hidden="true"><i></i></span>
      </button>
    </div>

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
      <div><span>{{ accumulate ? '已扫累计' : '当前商品' }}</span><strong>{{ accumulate ? (result.scan_total_objects ?? 0) : (result.object_count || 0) }}</strong></div>
      <div><span>{{ accumulate ? '画面内' : '采集到画面' }}</span><strong>{{ accumulate ? (result.object_count || 0) : Number(result.pipeline_latency_ms || 0).toFixed(0) + ' ms' }}</strong></div>
      <div><span>处理帧率</span><strong>{{ Number(result.fps || 0).toFixed(1) }} FPS</strong></div>
      <div><span>推理耗时</span><strong>{{ Number(result.inference_time_ms || 0).toFixed(0) }} ms</strong></div>
    </div>

    <div v-if="classes.length" class="camera-classes">
      <span v-for="item in classes" :key="item.name">{{ item.name }} <b>{{ item.count }}</b></span>
    </div>
    <p v-if="error" class="camera-error">{{ error }}</p>

    <footer class="camera-actions">
      <div>
        <span>{{ modelInfo }}</span>
        <small>{{ runtimeInfo }} · 已处理 {{ result.frame_count || 0 }} 帧 · 主动丢弃 {{ result.dropped_frames || 0 }} 个旧帧</small>
      </div>
      <div class="action-group">
        <el-button v-if="!active" type="primary" :loading="loading" @click="start">开始检测</el-button>
        <el-button v-else type="danger" plain @click="stop">停止检测</el-button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { VideoCamera } from '@element-plus/icons-vue'

const props = defineProps({
  sceneId: { type: Number, default: undefined },
  conf: { type: Number, default: 0.30 },
  iou: { type: Number, default: 0.45 },
  autoStart: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['result', 'status'])

const accumulate = ref(false)
const canvasRef = ref(null)
const active = ref(false)
const running = ref(false)
const loading = ref(false)
const hasFrame = ref(false)
const error = ref('')
const statusText = ref('等待启动')
const modelInfo = ref('模型将在连接后加载')
const runtimeInfo = ref('CPU 低延迟模式')
const result = ref({})
const defaultCameraUrl = 'http://127.0.0.1:18080'
const cameraUrl = ref(window.localStorage.getItem('visionpay-ip-webcam-url') || defaultCameraUrl)
let socket = null
let intentionalClose = false
let reconnectAttempts = 0
let reconnectTimer = null
let serverRejected = false
let pendingFrame = ''
let renderingFrame = false
let renderGeneration = 0

const classes = computed(() => Object.entries((accumulate.value ? result.value.scan_class_counts : result.value.class_counts) || {}).map(([name, count]) => ({ name, count })))

function saveCameraUrl() {
  const value = cameraUrl.value.trim()
  if (value) window.localStorage.setItem('visionpay-ip-webcam-url', value)
  else window.localStorage.removeItem('visionpay-ip-webcam-url')
}

function socketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/detection/camera`
}

function setStatus(value) {
  statusText.value = value
  emit('status', { active: active.value, running: running.value, loading: loading.value, error: error.value, text: value })
}

function decodeFrame(base64) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = reject
    image.src = `data:image/jpeg;base64,${base64}`
  })
}

async function renderLatestFrame(base64) {
  pendingFrame = base64
  if (renderingFrame) return
  renderingFrame = true
  const generation = renderGeneration
  const canvas = canvasRef.value
  try {
    while (pendingFrame && generation === renderGeneration) {
      const current = pendingFrame
      pendingFrame = ''
      const image = await decodeFrame(current)
      // A newer frame arrived while decoding: skip drawing the stale one.
      if (pendingFrame) continue
      if (!canvas || generation !== renderGeneration) break
      if (canvas.width !== image.naturalWidth) canvas.width = image.naturalWidth
      if (canvas.height !== image.naturalHeight) canvas.height = image.naturalHeight
      const context = canvas.getContext('2d', { alpha: false })
      if (context) {
        context.imageSmoothingEnabled = true
        context.imageSmoothingQuality = 'high'
        context.drawImage(image, 0, 0)
      }
      hasFrame.value = true
    }
  } catch {
    // A later WebSocket frame can recover rendering without reconnecting.
  } finally {
    renderingFrame = false
    if (pendingFrame) renderLatestFrame(pendingFrame)
  }
}

function connect() {
  window.clearTimeout(reconnectTimer)
  error.value = ''
  loading.value = true
  active.value = true
  running.value = false
  intentionalClose = false
  serverRejected = false
  setStatus('正在连接')
  socket = new WebSocket(socketUrl())
  socket.onopen = () => {
    setStatus('正在加载模型')
    socket.send(JSON.stringify({
      type: 'config',
      mode: 'cuda',
      conf: props.conf,
      iou: props.iou,
      scene_id: props.sceneId || null,
      camera_url: cameraUrl.value.trim(),
      accumulate: accumulate.value,
    }))
  }
  socket.onmessage = async (event) => {
    const message = JSON.parse(event.data)
    if (message.type === 'config_ok') {
      console.log('[camera] config_ok:', message)
      reconnectAttempts = 0
      loading.value = false
      running.value = true
      modelInfo.value = `${message.model} · ${message.scene}`
      runtimeInfo.value = `${message.image_size} × ${message.image_size} · 目标 ${Number(message.target_fps).toFixed(1)} FPS · ${accumulate.value ? '累计计数' : '瞬时计数'}`
      setStatus('实时识别中')
      return
    }
    if (message.type === 'result') {
      message.accumulate = accumulate.value
      result.value = message
      await nextTick()
      renderLatestFrame(message.annotated_frame)
      emit('result', message)
      return
    }
    if (message.type === 'error') {
      error.value = message.message || '实时检测失败'
      loading.value = false
      running.value = false
      active.value = false
      serverRejected = true
      setStatus('检测异常')
      socket?.close()
    }
  }
  socket.onerror = () => {
    error.value = '无法建立实时检测连接，请确认后端和 IP Webcam 已启动'
  }
  socket.onclose = (event) => {
    socket = null
    running.value = false
    loading.value = false
    if (event.code === 4001) {
      active.value = false
      serverRejected = true
      error.value = event.reason || '摄像头检测已由新的页面会话接管'
      setStatus('会话已被接管')
      return
    }
    if (serverRejected) {
      active.value = false
      setStatus('检测异常')
      return
    }
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
  if (!cameraUrl.value.trim()) {
    error.value = '请输入手机 IP Webcam 地址'
    setStatus('地址未填写')
    return
  }
  saveCameraUrl()
  reconnectAttempts = 0
  connect()
}

function stop() {
  intentionalClose = true
  active.value = false
  running.value = false
  loading.value = false
  window.clearTimeout(reconnectTimer)
  renderGeneration += 1
  pendingFrame = ''
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'close' }))
  socket?.close()
  socket = null
  setStatus('已停止')
}

function resetScan() {
  // 通知后端清空累计轨迹；本地展示一并归零，等待下一帧刷新。
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'reset_scan' }))
  result.value = {}
}

onMounted(() => { if (props.autoStart) start() })
onBeforeUnmount(stop)
defineExpose({ start, stop, resetScan })
</script>

<style lang="scss" scoped>
.ip-camera-panel {
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  box-shadow: $shadow-sm;
}

.camera-head {
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  color: $text-primary;
  background: $surface-muted;
  border-bottom: 1px solid $border-color;
  font-size: 11px;

  > div {
    display: flex;
    align-items: center;
    gap: 7px;
  }

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $text-placeholder;

    &.live {
      background: $success-color;
      box-shadow: 0 0 0 4px var(--vp-success-bg);
    }
  }

  small {
    color: $text-secondary;
  }
}

.camera-address {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid $border-color;
  background: $surface-muted;

  label {
    color: $text-primary;
    font-size: 11px;
    font-weight: 700;
  }

  small {
    color: $text-secondary;
    font-size: 9px;
  }

  .mode-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0;
    border: 0;
    background: transparent;
    color: $text-primary;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
    cursor: pointer;

    &:disabled {
      opacity: .5;
      cursor: not-allowed;
    }
  }

  .mode-switch {
    width: 32px;
    height: 18px;
    display: flex;
    align-items: center;
    padding: 2px;
    border-radius: 999px;
    background: #d2d2d7;
    transition: background .25s ease;

    i {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0, 0, 0, .2);
      transition: transform .25s cubic-bezier(.2, .8, .2, 1);
    }

    &.active {
      background: var(--vp-primary);
    }

    &.active i {
      transform: translateX(14px);
    }
  }
}

.camera-screen {
  position: relative;
  min-height: 360px;
  display: grid;
  place-items: center;
  overflow: hidden;
  // 浅色模式下用柔和灰底，暗色模式下仍为主题深色。
  background: $surface-muted;

  canvas {
    display: block;
    width: 100%;
    height: auto;
    max-width: 100%;
    max-height: 58vh;
    object-fit: contain;
  }
}

.camera-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: $text-secondary;
  text-align: center;

  .el-icon {
    font-size: 44px;
    color: $text-placeholder;
  }

  strong {
    color: $text-regular;
  }

  span {
    max-width: 430px;
    font-size: 11px;
    line-height: 1.6;
  }
}

.live-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 4px 7px;
  border-radius: 3px;
  color: #fff;
  background: $danger-color;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .08em;
}

.camera-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;

  > div {
    padding: 11px 13px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    border-right: 1px solid $border-color;

    &:last-child {
      border-right: 0;
    }
  }

  span {
    color: $text-secondary;
    font-size: 9px;
  }

  strong {
    color: $text-primary;
    font-size: 13px;
  }
}

.camera-classes {
  display: flex;
  gap: 6px;
  padding: 9px 12px;
  overflow-x: auto;
  background: $surface-muted;

  span {
    flex-shrink: 0;
    padding: 5px 8px;
    border: 1px solid $border-color;
    border-radius: 4px;
    background: $surface-color;
    color: $text-secondary;
    font-size: 10px;
  }

  b {
    margin-left: 4px;
    color: $text-primary;
  }
}

.camera-error {
  margin: 0;
  padding: 9px 13px;
  color: $danger-color;
  background: var(--vp-danger-bg);
  font-size: 11px;
}

.camera-actions {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;

  > div {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  span {
    overflow: hidden;
    color: $text-primary;
    font-size: 11px;
    font-weight: 700;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    color: $text-secondary;
    font-size: 9px;
  }
}

.camera-actions .action-group {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.camera-actions .action-group .el-button {
  flex-shrink: 0;
}

.compact {
  border-radius: 0;
  box-shadow: none;

  .camera-screen {
    min-height: 340px;
  }

  .camera-actions {
    border-top: 1px solid $border-color;
  }
}

@media (max-width: 640px) {
  .camera-address {
    grid-template-columns: 1fr;
    gap: 5px;
  }

  .camera-screen,
  .compact .camera-screen {
    min-height: 260px;
  }

  .camera-metrics {
    grid-template-columns: repeat(2, 1fr);
  }

  .camera-metrics > div:nth-child(2) {
    border-right: 0;
  }

  .camera-metrics > div:nth-child(-n+2) {
    border-bottom: 1px solid $border-color;
  }
}
</style>
