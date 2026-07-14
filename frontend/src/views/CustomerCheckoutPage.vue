<template>
  <div class="checkout-page">
    <header class="checkout-header">
      <div class="brand">
        <span class="brand-mark"><img src="/favicon.svg" alt="VisionPay" /></span>
        <div><strong>VisionPay</strong><span>自助视觉结算</span></div>
      </div>
      <div class="header-status"><i></i><span>设备就绪</span><small>原型模式</small></div>
    </header>

    <main class="checkout-main">
      <section class="capture-section">
        <div class="section-heading">
          <div><span>步骤 1</span><h1>扫描您的商品</h1></div>
          <button type="button" class="reset-button" @click="resetDemo"><el-icon><Refresh /></el-icon>重新扫描</button>
        </div>

        <div class="source-tabs" role="tablist">
          <button type="button" :class="{ active: sourceMode === 'camera' }" @click="selectSource('camera')"><el-icon><Camera /></el-icon>Webcam</button>
          <button type="button" :class="{ active: sourceMode === 'upload' }" @click="selectSource('upload')"><el-icon><UploadFilled /></el-icon>图片上传</button>
        </div>

        <div v-show="sourceMode === 'camera'" class="camera-stage">
          <div class="camera-toolbar"><span><i :class="{ inactive: !cameraConnected }"></i>{{ cameraStatusText }}</span><small>IP WEBCAM · MJPEG</small></div>
          <div class="camera-view">
            <img v-if="cameraStreamUrl" :src="cameraStreamUrl" alt="IP Webcam 实时画面" @load="handleCameraLoaded" @error="handleCameraError" />
            <div class="scan-frame"><span></span><span></span><span></span><span></span><b></b></div>
            <div v-if="!cameraConnected" class="camera-placeholder"><el-icon><Camera /></el-icon><strong>{{ cameraStreamUrl ? '正在连接手机摄像头' : '尚未连接 IP Webcam' }}</strong><span>先在手机启动服务器，再输入应用显示的局域网地址</span></div>
          </div>
          <div class="phone-connect-panel">
            <div><span>固定视频源</span><strong>{{ IP_WEBCAM_URL }}</strong></div>
            <button v-if="!cameraStreamUrl || !cameraConnected" type="button" @click="connectIpCamera">重新连接</button>
            <button v-else type="button" class="disconnect-button" @click="disconnectIpCamera">断开</button>
          </div>
          <p v-if="cameraError" class="camera-error">{{ cameraError }}</p>
          <div class="capture-tip"><el-icon><CircleCheckFilled /></el-icon><span>{{ cameraConnected ? '手机画面已接入，当前尚未发送至 YOLO' : '手机与电脑需连接同一个 Wi-Fi；推荐关闭 IP Webcam 的登录验证' }}</span></div>
        </div>

        <div v-show="sourceMode === 'upload'" class="upload-stage" @dragover.prevent @drop.prevent="handleDrop">
          <input ref="uploadInputRef" type="file" accept="image/*" hidden @change="handleUpload" />
          <img v-if="previewUrl" :src="previewUrl" alt="待识别商品预览" />
          <template v-else>
            <el-icon><UploadFilled /></el-icon>
            <strong>拖入或选择一张商品图片</strong>
            <span>支持 JPG、PNG、WEBP</span>
          </template>
          <button type="button" @click="uploadInputRef.click()">选择图片</button>
        </div>

        <div class="capture-footer">
          <div><span>识别状态</span><strong>{{ detectionStatus }}</strong></div>
          <div><span>画面内商品</span><strong>{{ totalItems }} 件</strong></div>
          <div><span>平均置信度</span><strong>{{ averageConfidence }}</strong></div>
        </div>
      </section>

      <section class="basket-section">
        <div class="basket-heading">
          <div><span>步骤 2</span><h2>确认商品清单</h2></div>
          <strong>{{ totalItems }} 件</strong>
        </div>

        <div v-if="products.length && !pricingComplete" class="price-notice"><el-icon><InfoFilled /></el-icon><span>{{ unpricedItems }} 件商品尚未配置价格，请先在价目表中补齐后再结算。</span></div>
        <div v-else-if="detectionError" class="price-notice"><el-icon><InfoFilled /></el-icon><span>{{ detectionError }}</span></div>

        <div class="product-list">
          <article v-for="item in products" :key="item.classId" class="product-item">
            <div class="product-thumb"><span>{{ item.short }}</span></div>
            <div class="product-copy">
              <strong>{{ item.name }}</strong>
              <span>{{ item.category }} · 置信度 {{ item.confidence }}</span>
              <b v-if="item.hasPrice">{{ formatMoney(item.unitPrice) }} / 件 · 小计 {{ formatMoney(item.unitPrice * item.quantity) }}</b>
              <b v-else>价格未配置</b>
            </div>
            <div class="quantity-control">
              <button type="button" :disabled="item.quantity <= 1 || pricing" @click="changeQuantity(item, -1)"><el-icon><Minus /></el-icon></button>
              <span>{{ item.quantity }}</span>
              <button type="button" :disabled="pricing" @click="changeQuantity(item, 1)"><el-icon><Plus /></el-icon></button>
            </div>
            <button type="button" class="remove-button" aria-label="移除商品" @click="removeProduct(item.classId)"><el-icon><Delete /></el-icon></button>
          </article>

          <div v-if="!products.length" class="empty-basket"><el-icon><ShoppingCart /></el-icon><strong>暂未识别到商品</strong><span>请重新扫描或上传商品图片</span></div>
        </div>

        <footer class="settlement-panel">
          <div class="settlement-summary"><span>应付金额</span><strong>{{ formatMoney(totalPrice) }}</strong><small>{{ pricing ? '正在重新计价' : pricingComplete ? '价格已由服务端按当前数量计算' : '总价不含未定价商品' }}</small></div>
          <button type="button" :disabled="!products.length || !pricingComplete || detecting || pricing || creatingOrder" @click="goToPayment"><span>{{ creatingOrder ? '正在创建支付订单' : '确认商品并去结算' }}</span><el-icon><ArrowRight /></el-icon></button>
          <p>继续即表示您已确认以上商品和数量</p>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Camera, CircleCheckFilled, Delete, InfoFilled, Minus, Plus, Refresh, ShoppingCart, UploadFilled } from '@element-plus/icons-vue'
import { calculateCheckoutApi, createMockPaymentOrderApi, detectCheckoutApi } from '@/api/checkout'

const router = useRouter()
const sourceMode = ref('camera')
const uploadInputRef = ref(null)
const previewUrl = ref('')
const IP_WEBCAM_URL = 'http://192.168.1.109:8080'
const cameraStreamUrl = ref('')
const cameraConnected = ref(false)
const cameraStatusText = ref('等待连接')
const cameraError = ref('')
const detecting = ref(false)
const pricing = ref(false)
const creatingOrder = ref(false)
const detectionResult = ref(null)
const checkoutSummary = ref(null)
const detectionError = ref('')
let cameraConnectTimer = null
let detectionSequence = 0
let pricingSequence = 0
const products = ref([])
const totalItems = computed(() => products.value.reduce((sum, item) => sum + item.quantity, 0))
const totalPrice = computed(() => Number(checkoutSummary.value?.total_price || 0))
const unpricedItems = computed(() => Number(checkoutSummary.value?.unpriced_objects || 0))
const pricingComplete = computed(() => products.value.length > 0 && checkoutSummary.value?.pricing_complete === true)
const detectionStatus = computed(() => detecting.value ? '识别中' : detectionError.value ? '识别失败' : detectionResult.value ? '已完成' : '待扫描')
const averageConfidence = computed(() => {
  const detections = detectionResult.value?.items?.flatMap((item) => item.detections || []) || []
  if (!detections.length) return '--'
  return `${(detections.reduce((sum, item) => sum + Number(item.confidence || 0), 0) / detections.length * 100).toFixed(1)}%`
})

async function setPreview(file) {
  if (!file?.type?.startsWith('image/')) return
  const sequence = ++detectionSequence
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
  detecting.value = true
  detectionError.value = ''
  products.value = []
  checkoutSummary.value = null
  try {
    const result = await detectCheckoutApi(file)
    if (sequence !== detectionSequence) return
    detectionResult.value = result
    checkoutSummary.value = result.price_summary
    const confidences = new Map()
    for (const detection of result.items?.flatMap((item) => item.detections || []) || []) {
      const values = confidences.get(detection.class_id) || []
      values.push(Number(detection.confidence || 0))
      confidences.set(detection.class_id, values)
    }
    products.value = (result.price_summary?.items || []).map((item) => {
      const values = confidences.get(item.class_id) || []
      const confidence = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
      const displayName = item.name || item.sku_name || item.class_name || `商品 ${item.class_id}`
      return {
        classId: item.class_id,
        name: displayName,
        category: item.class_name,
        confidence: `${(confidence * 100).toFixed(1)}%`,
        short: displayName.slice(0, 2),
        quantity: item.count,
        unitPrice: Number(item.unit_price || 0),
        hasPrice: Boolean(item.has_price),
        currency: item.currency || 'CNY',
        barcode: item.barcode || '',
      }
    })
    if (!products.value.length) ElMessage.warning('当前阈值下未识别到商品')
  } catch {
    if (sequence !== detectionSequence) return
    detectionResult.value = null
    detectionError.value = '商品识别失败，请检查检测模型和场景配置后重试。'
  } finally {
    if (sequence === detectionSequence) detecting.value = false
  }
}
function handleUpload(event) { setPreview(event.target.files?.[0]); event.target.value = '' }
function handleDrop(event) { setPreview(event.dataTransfer.files?.[0]) }
async function recalculateCart() {
  const sequence = ++pricingSequence
  if (!products.value.length) {
    checkoutSummary.value = { total_price: 0, pricing_complete: true, unpriced_objects: 0, items: [] }
    return
  }
  pricing.value = true
  try {
    const summary = await calculateCheckoutApi(products.value)
    if (sequence !== pricingSequence) return
    checkoutSummary.value = summary
    const serverItems = new Map((summary.items || []).map((item) => [item.class_id, item]))
    for (const product of products.value) {
      const serverItem = serverItems.get(product.classId)
      if (!serverItem) continue
      product.unitPrice = Number(serverItem.unit_price || 0)
      product.hasPrice = Boolean(serverItem.has_price)
      product.name = serverItem.name || serverItem.sku_name || product.name
      product.barcode = serverItem.barcode || ''
    }
  } finally {
    if (sequence === pricingSequence) pricing.value = false
  }
}
async function changeQuantity(item, delta) {
  const previous = item.quantity
  item.quantity = Math.max(1, Math.min(99, item.quantity + delta))
  if (item.quantity === previous) return
  try { await recalculateCart() }
  catch { item.quantity = previous }
}
async function removeProduct(classId) {
  const previous = products.value
  products.value = products.value.filter((item) => item.classId !== classId)
  try { await recalculateCart() }
  catch { products.value = previous }
}
function resetDemo() { detectionSequence++; pricingSequence++; detecting.value = false; pricing.value = false; products.value = []; detectionResult.value = null; checkoutSummary.value = null; detectionError.value = ''; selectSource('camera'); if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function formatMoney(value) { return `¥ ${Number(value || 0).toFixed(2)}` }
async function goToPayment() {
  const order = { items: products.value, itemCount: totalItems.value, totalPrice: totalPrice.value, currency: 'CNY' }
  sessionStorage.setItem('visionpay-checkout-order', JSON.stringify(order))
  creatingOrder.value = true
  try {
    const paymentOrder = await createMockPaymentOrderApi(products.value)
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder))
    router.push({ path: '/checkout/payment', query: { token: paymentOrder.payment_token } })
  } finally {
    creatingOrder.value = false
  }
}
function connectIpCamera() {
  cameraError.value = ''
  cameraConnected.value = false
  cameraStatusText.value = '正在连接'
  cameraStreamUrl.value = `/api/camera/ip-webcam/stream?url=${encodeURIComponent(IP_WEBCAM_URL)}&t=${Date.now()}`
  window.clearTimeout(cameraConnectTimer)
  cameraConnectTimer = window.setTimeout(() => {
    if (!cameraConnected.value && cameraStreamUrl.value) handleCameraError()
  }, 8000)
}
function handleCameraLoaded() { window.clearTimeout(cameraConnectTimer); cameraConnected.value = true; cameraStatusText.value = '实时画面' }
function handleCameraError() { window.clearTimeout(cameraConnectTimer); cameraConnected.value = false; cameraStatusText.value = '连接失败'; cameraError.value = '无法读取视频流，请确认手机已点击“启动服务器”、地址正确且两台设备在同一 Wi-Fi' }
function disconnectIpCamera() { window.clearTimeout(cameraConnectTimer); cameraStreamUrl.value = ''; cameraConnected.value = false; cameraStatusText.value = '等待连接'; cameraError.value = '' }
function selectSource(mode) { sourceMode.value = mode; if (mode === 'camera') connectIpCamera(); else disconnectIpCamera() }
onMounted(connectIpCamera)
onBeforeUnmount(() => { detectionSequence++; pricingSequence++; if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); disconnectIpCamera() })
</script>

<style lang="scss" scoped>
.checkout-page { min-height: 100vh; color: #17212b; background: #eef1f4; }
.checkout-header { height: 74px; display: flex; align-items: center; justify-content: space-between; padding: 0 34px; border-bottom: 1px solid #d9e0e6; background: #fff; }.brand { display: flex; align-items: center; gap: 12px; }.brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 7px; background: #1d4ed8; }.brand-mark img { width: 22px; filter: brightness(0) invert(1); }.brand > div { display: flex; flex-direction: column; }.brand strong { font-size: 18px; }.brand span { color: #70808f; font-size: 11px; }.header-status { display: grid; grid-template-columns: 8px auto auto; align-items: center; gap: 7px; color: #3a4a58; font-size: 12px; }.header-status i { width: 8px; height: 8px; border-radius: 50%; background: #16a36d; box-shadow: 0 0 0 4px #e0f5ec; }.header-status small { margin-left: 6px; padding-left: 12px; border-left: 1px solid #dce2e7; color: #82909d; }
.checkout-main { min-height: calc(100vh - 74px); display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(390px, .65fr); }.capture-section { min-width: 0; padding: 28px 30px 32px; border-right: 1px solid #d8dfe5; }.section-heading, .basket-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }.section-heading > div, .basket-heading > div { display: flex; flex-direction: column; gap: 4px; }.section-heading span, .basket-heading span { color: #1d4ed8; font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }.section-heading h1, .basket-heading h2 { margin: 0; font-size: 23px; letter-spacing: -.02em; }.reset-button { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid #cfd8df; border-radius: 5px; color: #526170; background: #fff; cursor: pointer; font-size: 12px; }.reset-button:hover { border-color: #1d4ed8; color: #1d4ed8; }
.source-tabs { display: inline-grid; grid-template-columns: 1fr 1fr; margin-bottom: 12px; border: 1px solid #cfd8df; border-radius: 6px; overflow: hidden; }.source-tabs button { display: flex; align-items: center; justify-content: center; gap: 7px; min-width: 150px; height: 40px; border: 0; border-right: 1px solid #cfd8df; color: #657482; background: #fff; cursor: pointer; }.source-tabs button:last-child { border-right: 0; }.source-tabs button.active { color: #fff; background: #1d4ed8; }
.camera-stage, .upload-stage { border: 1px solid #cbd4dc; background: #fff; }.camera-toolbar { height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid #2f3d49; color: #dfe7ec; background: #1e2a34; font-size: 11px; }.camera-toolbar span { display: flex; align-items: center; gap: 7px; }.camera-toolbar i { width: 7px; height: 7px; border-radius: 50%; background: #2bd88f; }.camera-toolbar i.inactive { background: #71808c; }.camera-toolbar small { color: #8fa0ad; }.camera-view { position: relative; aspect-ratio: 16 / 9; min-height: 340px; display: grid; place-items: center; overflow: hidden; background: #17212a; }.camera-view > img { width: 100%; height: 100%; object-fit: contain; }.camera-placeholder { position: absolute; display: flex; flex-direction: column; align-items: center; gap: 7px; color: #aebbc5; }.camera-placeholder .el-icon { font-size: 42px; color: #657682; }.camera-placeholder strong { color: #d8e1e7; font-size: 14px; }.camera-placeholder span { font-size: 11px; }.scan-frame { position: absolute; inset: 13%; z-index: 2; pointer-events: none; }.scan-frame > span { position: absolute; width: 38px; height: 38px; border-color: #48d79f; border-style: solid; }.scan-frame > span:nth-child(1) { top: 0; left: 0; border-width: 3px 0 0 3px; }.scan-frame > span:nth-child(2) { top: 0; right: 0; border-width: 3px 3px 0 0; }.scan-frame > span:nth-child(3) { bottom: 0; left: 0; border-width: 0 0 3px 3px; }.scan-frame > span:nth-child(4) { right: 0; bottom: 0; border-width: 0 3px 3px 0; }.scan-frame b { position: absolute; top: 48%; left: 4%; right: 4%; height: 1px; background: #48d79f; opacity: .7; }.phone-connect-panel { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 14px; border-top: 1px solid #dce3e8; }.phone-connect-panel > div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }.phone-connect-panel span { color: #82909d; font-size: 9px; }.phone-connect-panel strong { overflow: hidden; color: #273643; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.phone-connect-panel button { flex-shrink: 0; height: 34px; padding: 0 12px; border: 1px solid #1d4ed8; border-radius: 5px; color: #fff; background: #1d4ed8; cursor: pointer; font-size: 11px; }.phone-connect-panel button.disconnect-button { border-color: #cbd5df; color: #52616e; background: #fff; }.camera-error { margin: 0; padding: 9px 14px; color: #9c2938; background: #fff0f2; font-size: 11px; }.capture-tip { height: 45px; display: flex; align-items: center; gap: 8px; padding: 0 14px; color: #476050; background: #effaf5; font-size: 12px; }.capture-tip .el-icon { color: #16a36d; }
.upload-stage { min-height: 440px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; border-style: dashed; color: #6f7f8d; }.upload-stage > .el-icon { font-size: 40px; color: #1d4ed8; }.upload-stage strong { color: #273643; font-size: 15px; }.upload-stage span { font-size: 11px; }.upload-stage button { margin-top: 8px; padding: 9px 18px; border: 0; border-radius: 5px; color: #fff; background: #1d4ed8; cursor: pointer; }.upload-stage img { max-width: 90%; max-height: 350px; object-fit: contain; }
.capture-footer { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 14px; border: 1px solid #d4dce3; background: #fff; }.capture-footer div { display: flex; flex-direction: column; gap: 4px; padding: 13px 15px; border-right: 1px solid #dfe5ea; }.capture-footer div:last-child { border-right: 0; }.capture-footer span { color: #7b8996; font-size: 10px; }.capture-footer strong { font-size: 14px; }
.basket-section { min-width: 0; display: flex; flex-direction: column; padding: 28px 28px 24px; background: #fff; }.basket-heading { margin-bottom: 14px; }.basket-heading > strong { min-width: 42px; padding: 6px 8px; border-radius: 999px; color: #1d4ed8; background: #eaf0ff; text-align: center; font-size: 12px; }.price-notice { display: flex; align-items: flex-start; gap: 8px; padding: 10px 11px; border-left: 3px solid #e49a24; color: #79591d; background: #fff8e9; font-size: 11px; line-height: 1.55; }.price-notice .el-icon { margin-top: 2px; flex-shrink: 0; }.product-list { min-height: 0; flex: 1; overflow-y: auto; margin: 15px -5px 15px 0; padding-right: 5px; }.product-item { position: relative; display: grid; grid-template-columns: 54px minmax(0, 1fr) auto 27px; align-items: center; gap: 11px; padding: 13px 0; border-bottom: 1px solid #e5e9ed; }.product-thumb { width: 54px; height: 54px; display: grid; place-items: center; border: 1px solid #dce3e8; border-radius: 6px; color: #1d4ed8; background: #f2f6ff; font-size: 10px; font-weight: 800; }.product-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }.product-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }.product-copy span { color: #82909d; font-size: 10px; }.product-copy b { color: #b07818; font-size: 11px; }.quantity-control { display: grid; grid-template-columns: 26px 30px 26px; align-items: center; border: 1px solid #d5dde4; border-radius: 5px; overflow: hidden; }.quantity-control button { height: 28px; border: 0; color: #52616e; background: #f6f8fa; cursor: pointer; }.quantity-control button:disabled { color: #bdc5cb; cursor: not-allowed; }.quantity-control span { text-align: center; font-size: 12px; font-weight: 800; }.remove-button { width: 27px; height: 27px; border: 0; color: #97a2ab; background: transparent; cursor: pointer; }.remove-button:hover { color: #d44c5c; }.empty-basket { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #84919c; }.empty-basket .el-icon { font-size: 38px; }.empty-basket strong { color: #53616d; }.empty-basket span { font-size: 11px; }
.settlement-panel { padding-top: 18px; border-top: 1px solid #dce2e7; }.settlement-summary { display: grid; grid-template-columns: 1fr auto; align-items: end; margin-bottom: 14px; }.settlement-summary span { color: #52616e; font-size: 13px; }.settlement-summary strong { grid-row: span 2; color: #152331; font-size: 28px; }.settlement-summary small { color: #9a6a16; font-size: 10px; }.settlement-panel > button { width: 100%; height: 50px; display: flex; align-items: center; justify-content: center; gap: 10px; border: 0; border-radius: 6px; color: #fff; background: #1d4ed8; cursor: pointer; font-size: 15px; font-weight: 800; }.settlement-panel > button:hover { background: #173fae; }.settlement-panel > button:disabled { background: #aeb9c5; cursor: not-allowed; }.settlement-panel p { margin: 9px 0 0; color: #919ca6; text-align: center; font-size: 10px; }
@media (max-width: 1050px) { .checkout-main { grid-template-columns: 1fr; }.capture-section { border-right: 0; border-bottom: 1px solid #d8dfe5; }.basket-section { min-height: 620px; }.camera-view { min-height: 0; } }
@media (max-width: 640px) { .checkout-header { height: 66px; padding: 0 16px; }.header-status small { display: none; }.checkout-main { min-height: calc(100vh - 66px); }.capture-section, .basket-section { padding: 20px 16px; }.section-heading h1, .basket-heading h2 { font-size: 20px; }.source-tabs { width: 100%; }.source-tabs button { min-width: 0; }.capture-footer { grid-template-columns: 1fr; }.capture-footer div { border-right: 0; border-bottom: 1px solid #dfe5ea; }.capture-footer div:last-child { border-bottom: 0; }.product-item { grid-template-columns: 48px minmax(0, 1fr) 27px; }.product-thumb { width: 48px; height: 48px; }.quantity-control { grid-column: 2 / 3; justify-self: start; }.remove-button { grid-column: 3; grid-row: 1; } }
</style>
