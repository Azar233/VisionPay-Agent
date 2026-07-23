<template>
  <div :class="['checkout-page', { 'is-customer-mode': customerModeActive }]">
    <header class="checkout-header">
      <div class="brand">
        <span class="brand-mark"><img src="/favicon.svg" alt="VisionPay" /></span>
        <div><strong>VisionPay</strong><span>自助视觉结算</span></div>
      </div>
      <div class="header-actions">
        <button
          v-if="!customerModeActive"
          type="button"
          class="history-button"
          @click="router.push('/checkout/history')"
        >
          <el-icon><List /></el-icon>订单历史
        </button>
        <div class="header-status"><i></i><span>设备就绪</span></div>
      </div>
    </header>

    <main class="checkout-main">
      <section class="capture-section card-container">
        <div class="section-heading">
          <div>
            <span>步骤 1</span>
            <h1>扫描您的商品</h1>
          </div>
          <button type="button" class="reset-button" @click="resetDemo">
            <el-icon><Refresh /></el-icon>重新扫描
          </button>
        </div>

        <div class="source-tabs" role="tablist">
          <button
            type="button"
            :class="{ active: sourceMode === 'camera' }"
            @click="selectSource('camera')"
          >
            <el-icon><Camera /></el-icon>Webcam
          </button>
          <button
            type="button"
            :class="{ active: sourceMode === 'upload' }"
            @click="selectSource('upload')"
          >
            <el-icon><UploadFilled /></el-icon>图片上传
          </button>
        </div>

        <div v-if="sourceMode === 'camera'" class="camera-stage">
          <IpCameraDetectionPanel
            ref="cameraDetectionRef"
            compact
            auto-start
            @result="applyRealtimeDetection"
            @status="handleCameraStatus"
          />
        </div>

        <div
          v-show="sourceMode === 'upload'"
          class="upload-stage"
          @dragover.prevent
          @drop.prevent="handleDrop"
        >
          <input ref="uploadInputRef" type="file" accept="image/*" hidden @change="handleUpload" />
          <img v-if="previewUrl" :src="uploadDisplayImage" :alt="uploadImageAlt" />
          <template v-else>
            <el-icon><UploadFilled /></el-icon>
            <strong>拖入或选择一张商品图片</strong>
            <span>支持 JPG、PNG、WEBP</span>
          </template>
          <button
            v-if="!selectedUploadFile"
            type="button"
            class="select-image-button"
            @click="openUploadPicker"
          >
            选择图片
          </button>
          <div v-else class="upload-actions">
            <button type="button" class="secondary" :disabled="detecting" @click="openUploadPicker">
              重新选择
            </button>
            <button
              type="button"
              class="primary"
              :disabled="detecting"
              @click="startUploadDetection"
            >
              {{ uploadDetectionButtonText }}
            </button>
          </div>
        </div>

        <div class="capture-footer">
          <div>
            <span>识别状态</span><strong class="status-pill">{{ detectionStatus }}</strong>
          </div>
          <div>
            <span>画面内商品</span><strong>{{ totalItems }} 件</strong>
          </div>
          <div>
            <span>平均置信度</span><strong>{{ averageConfidence }}</strong>
          </div>
        </div>
      </section>

      <section class="basket-section card-container">
        <div class="basket-heading">
          <div>
            <span>步骤 2</span>
            <h2>确认商品清单</h2>
          </div>
          <strong class="item-count-pill">{{ totalItems }} 件</strong>
        </div>

        <div v-if="products.length && !pricingComplete" class="price-notice">
          <el-icon><InfoFilled /></el-icon
          ><span>{{ unpricedItems }} 件商品尚未配置价格，请先在价目表中补齐后再结算。</span>
        </div>
        <div v-else-if="detectionError" class="price-notice">
          <el-icon><InfoFilled /></el-icon><span>{{ detectionError }}</span>
        </div>

        <div class="product-list">
          <article v-for="item in products" :key="item.classId" class="product-item">
            <div class="product-thumb">
              <span>{{ item.short }}</span>
            </div>
            <div class="product-copy">
              <strong>{{ item.name }}</strong>
              <span>{{ item.category }} · 置信度 {{ item.confidence }}</span>
              <b v-if="item.hasPrice"
                >{{ formatMoney(item.unitPrice) }} / 件 · 小计
                {{ formatMoney(item.unitPrice * item.quantity) }}</b
              >
              <b v-else>价格未配置</b>
            </div>
            <div class="quantity-control">
              <button
                type="button"
                :disabled="item.quantity <= 1 || pricing"
                @click="changeQuantity(item, -1)"
              >
                <el-icon><Minus /></el-icon>
              </button>
              <span>{{ item.quantity }}</span>
              <button type="button" :disabled="pricing" @click="changeQuantity(item, 1)">
                <el-icon><Plus /></el-icon>
              </button>
            </div>
            <button
              type="button"
              class="remove-button"
              aria-label="移除商品"
              @click="removeProduct(item.classId)"
            >
              <el-icon><Delete /></el-icon>
            </button>
          </article>

          <div v-if="!products.length" class="empty-basket">
            <el-icon><ShoppingCart /></el-icon><strong>暂未识别到商品</strong
            ><span>请重新扫描或上传商品图片</span>
          </div>
        </div>

        <footer class="settlement-panel">
          <div class="settlement-summary">
            <span>应付金额</span><strong>{{ formatMoney(totalPrice) }}</strong
            ><small>{{
              pricing
                ? '正在重新计价'
                : pricingComplete
                  ? '价格已由服务端按当前数量计算'
                  : '总价不含未定价商品'
            }}</small>
          </div>
          <button
            type="button"
            :disabled="
              !products.length || !pricingComplete || detecting || pricing || creatingOrder
            "
            @click="goToPayment"
          >
            <span>{{ creatingOrder ? '正在创建支付订单' : '确认商品并去结算' }}</span
            ><el-icon><ArrowRight /></el-icon>
          </button>
          <p>继续即表示您已确认以上商品和数量</p>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  Camera,
  Delete,
  InfoFilled,
  List,
  Minus,
  Plus,
  Refresh,
  ShoppingCart,
  UploadFilled,
} from '@element-plus/icons-vue'
import { calculateCheckoutApi, createMockPaymentOrderApi, detectCheckoutApi } from '@/api/checkout'
import IpCameraDetectionPanel from '@/components/IpCameraDetectionPanel.vue'
import { useCustomerModeStore } from '@/stores/customerMode'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const customerModeStore = useCustomerModeStore()
const customerModeActive = computed(() => customerModeStore.isActiveFor(userStore.user?.id))
const sourceMode = ref('camera')
const uploadInputRef = ref(null)
const selectedUploadFile = ref(null)
const previewUrl = ref('')
const cameraDetectionRef = ref(null)
const cameraState = ref({ loading: false, running: false, error: '' })
const detecting = ref(false)
const pricing = ref(false)
const creatingOrder = ref(false)
const detectionResult = ref(null)
const checkoutSummary = ref(null)
const activeModelVersionId = ref(null)
const detectionError = ref('')
let detectionSequence = 0
let pricingSequence = 0
const products = ref([])
// 摄像头累计模式：服务端扫描计数为基准；手动调整以增量叠加，移除的类别在重置前隐藏。
const manualDeltas = ref({})
const removedClasses = ref(new Set())
const confidenceMemory = {}
const totalItems = computed(() => products.value.reduce((sum, item) => sum + item.quantity, 0))
const totalPrice = computed(() => Number(checkoutSummary.value?.total_price || 0))
const unpricedItems = computed(() => Number(checkoutSummary.value?.unpriced_objects || 0))
const pricingComplete = computed(
  () => products.value.length > 0 && checkoutSummary.value?.pricing_complete === true,
)
const detectionStatus = computed(() => {
  if (sourceMode.value === 'camera') {
    if (cameraState.value.running) return '实时识别中'
    if (cameraState.value.loading) return '识别中'
  }
  if (detecting.value) return '识别中'
  if (detectionError.value) return '识别失败'
  if (detectionResult.value?.source === sourceMode.value) return '已完成'
  if (sourceMode.value === 'upload' && selectedUploadFile.value) return '待识别'
  return '待扫描'
})
const uploadDetectionButtonText = computed(() => {
  if (detecting.value) return '正在识别'
  if (detectionResult.value?.source === 'upload' || detectionError.value) return '重新识别'
  return '开始识别'
})
const uploadDisplayImage = computed(() => {
  if (detectionResult.value?.source !== 'upload') return previewUrl.value
  return detectionResult.value.items?.[0]?.annotated_image || previewUrl.value
})
const uploadImageAlt = computed(() =>
  detectionResult.value?.source === 'upload' ? '商品检测标注结果' : '待识别商品预览',
)
const averageConfidence = computed(() => {
  const detections = detectionResult.value?.items?.flatMap((item) => item.detections || []) || []
  if (!detections.length) return '--'
  return `${((detections.reduce((sum, item) => sum + Number(item.confidence || 0), 0) / detections.length) * 100).toFixed(1)}%`
})

function productsFromDetection(detections, priceSummary) {
  const confidences = new Map()
  for (const detection of detections || []) {
    const values = confidences.get(detection.class_id) || []
    values.push(Number(detection.confidence || 0))
    confidences.set(detection.class_id, values)
  }
  return (priceSummary?.items || []).map((item) => {
    const values = confidences.get(item.class_id) || []
    const confidence = values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : 0
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
}

function applyRealtimeDetection(result) {
  if (sourceMode.value !== 'camera') return
  const item = { filename: 'IP Webcam 当前帧', detections: result.detections || [] }
  detectionResult.value = { source: 'camera', items: [item] }
  activeModelVersionId.value = result.model_version_id || null
  if (!result.accumulate) {
    // 瞬时模式：每帧覆盖购物车，只保留当前画面物品。
    manualDeltas.value = {}
    removedClasses.value = new Set()
    Object.keys(confidenceMemory).forEach((key) => delete confidenceMemory[key])
    checkoutSummary.value = result.price_summary
    products.value = productsFromDetection(item.detections, result.price_summary)
    detectionError.value = ''
    return
  }
  // 累计模式：服务端扫描计数为基准，手动调整以增量叠加，移除的类别在重置前隐藏。
  for (const detection of item.detections) {
    const values =
      confidenceMemory[detection.class_id] || (confidenceMemory[detection.class_id] = [])
    values.push(Number(detection.confidence || 0))
    if (values.length > 5) values.shift()
  }
  const scanSummary = result.price_summary
  const nextProducts = productsFromDetection(item.detections, scanSummary).filter(
    (product) => !removedClasses.value.has(product.classId),
  )
  let adjusted = false
  for (const product of nextProducts) {
    const remembered = confidenceMemory[product.classId]
    if (remembered?.length) {
      product.confidence = `${((remembered.reduce((sum, value) => sum + value, 0) / remembered.length) * 100).toFixed(1)}%`
    }
    const delta = manualDeltas.value[product.classId] || 0
    if (delta) {
      product.quantity = Math.max(1, product.quantity + delta)
      adjusted = true
    }
  }
  products.value = nextProducts
  if (adjusted) {
    if ((result.new_confirmed || []).length || !checkoutSummary.value) recalculateCart()
  } else {
    checkoutSummary.value = scanSummary
  }
  detectionError.value = ''
}

function handleCameraStatus(status) {
  cameraState.value = status
  detecting.value = status.loading
  if (status.error) detectionError.value = status.error
}

function selectUploadImage(file) {
  const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
  if (!file || !allowedTypes.has(file.type)) {
    ElMessage.warning('请选择 JPG、PNG 或 WEBP 格式的图片')
    return
  }
  detectionSequence++
  pricingSequence++
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  selectedUploadFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  detecting.value = false
  pricing.value = false
  detectionError.value = ''
  detectionResult.value = null
  activeModelVersionId.value = null
  products.value = []
  checkoutSummary.value = null
}

async function startUploadDetection() {
  const file = selectedUploadFile.value
  if (!file || detecting.value) return
  const sequence = ++detectionSequence
  detecting.value = true
  detectionError.value = ''
  detectionResult.value = null
  activeModelVersionId.value = null
  products.value = []
  checkoutSummary.value = null
  try {
    const result = await detectCheckoutApi(file)
    if (sequence !== detectionSequence) return
    detectionResult.value = { ...result, source: 'upload' }
    activeModelVersionId.value = result.model_version_id || null
    checkoutSummary.value = result.price_summary
    products.value = productsFromDetection(
      result.items?.flatMap((item) => item.detections || []) || [],
      result.price_summary,
    )
    if (!products.value.length) ElMessage.warning('当前阈值下未识别到商品')
  } catch {
    if (sequence !== detectionSequence) return
    detectionResult.value = null
    detectionError.value = '商品识别失败，请检查检测模型和场景配置后重试。'
  } finally {
    if (sequence === detectionSequence) detecting.value = false
  }
}
function openUploadPicker() {
  if (!detecting.value) uploadInputRef.value?.click()
}
function handleUpload(event) {
  selectUploadImage(event.target.files?.[0])
  event.target.value = ''
}
function handleDrop(event) {
  if (!detecting.value) selectUploadImage(event.dataTransfer.files?.[0])
}
async function recalculateCart() {
  const sequence = ++pricingSequence
  if (!products.value.length) {
    checkoutSummary.value = {
      total_price: 0,
      pricing_complete: true,
      unpriced_objects: 0,
      items: [],
    }
    return
  }
  pricing.value = true
  try {
    const summary = await calculateCheckoutApi(products.value, activeModelVersionId.value)
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
  const applied = item.quantity - previous
  if (sourceMode.value === 'camera')
    manualDeltas.value[item.classId] = (manualDeltas.value[item.classId] || 0) + applied
  try {
    await recalculateCart()
  } catch {
    if (sourceMode.value === 'camera') manualDeltas.value[item.classId] -= applied
    item.quantity = previous
  }
}
async function removeProduct(classId) {
  const previous = products.value
  const previousDelta = manualDeltas.value[classId]
  products.value = products.value.filter((item) => item.classId !== classId)
  if (sourceMode.value === 'camera') {
    removedClasses.value.add(classId)
    delete manualDeltas.value[classId]
  }
  try {
    await recalculateCart()
  } catch {
    products.value = previous
    if (sourceMode.value === 'camera') {
      removedClasses.value.delete(classId)
      if (previousDelta) manualDeltas.value[classId] = previousDelta
    }
  }
}
function resetDemo() {
  detectionSequence++
  pricingSequence++
  detecting.value = false
  pricing.value = false
  products.value = []
  detectionResult.value = null
  checkoutSummary.value = null
  activeModelVersionId.value = null
  detectionError.value = ''
  selectedUploadFile.value = null
  manualDeltas.value = {}
  removedClasses.value = new Set()
  Object.keys(confidenceMemory).forEach((key) => delete confidenceMemory[key])
  if (sourceMode.value === 'camera') {
    cameraDetectionRef.value?.resetScan()
    cameraDetectionRef.value?.start()
  } else selectSource('camera')
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}
function formatMoney(value) {
  return `¥ ${Number(value || 0).toFixed(2)}`
}
async function goToPayment() {
  const order = {
    items: products.value,
    itemCount: totalItems.value,
    totalPrice: totalPrice.value,
    currency: 'CNY',
    modelVersionId: activeModelVersionId.value,
  }
  sessionStorage.setItem('visionpay-checkout-order', JSON.stringify(order))
  creatingOrder.value = true
  try {
    const paymentOrder = await createMockPaymentOrderApi(products.value, activeModelVersionId.value)
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder))
    router.push({ path: '/checkout/payment', query: { token: paymentOrder.payment_token } })
  } finally {
    creatingOrder.value = false
  }
}
function selectSource(mode) {
  if (sourceMode.value === mode) return
  detectionSequence++
  pricingSequence++
  detecting.value = false
  pricing.value = false
  detectionResult.value = null
  checkoutSummary.value = null
  activeModelVersionId.value = null
  detectionError.value = ''
  products.value = []
  manualDeltas.value = {}
  removedClasses.value = new Set()
  Object.keys(confidenceMemory).forEach((key) => delete confidenceMemory[key])
  sourceMode.value = mode
}
onBeforeUnmount(() => {
  detectionSequence++
  pricingSequence++
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  cameraDetectionRef.value?.stop()
})
</script>

<style lang="scss" scoped>
.checkout-page {
  min-height: 100vh;
  color: $text-primary;
  background: $bg-color;
}

.checkout-header {
  height: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 34px;
  border-bottom: 1px solid $border-color;
  background: $surface-color;
  box-shadow: $shadow-sm;
}

.checkout-page.is-customer-mode .checkout-header {
  padding-right: 220px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;

  .brand-mark {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: $border-radius-sm;
    background: $primary-color;

    img {
      width: 22px;
      filter: brightness(0) invert(1);
    }
  }

  > div {
    display: flex;
    flex-direction: column;
  }

  strong {
    color: $text-primary;
    font-size: 18px;
  }

  span {
    color: $text-secondary;
    font-size: 11px;
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.history-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  color: $text-secondary;
  background: $surface-color;
  cursor: pointer;
  font-size: 12px;
  transition:
    border-color 0.2s,
    color 0.2s,
    background 0.2s;

  &:hover {
    border-color: $primary-color;
    color: $primary-color;
    background: $primary-soft;
  }
}

.header-status {
  display: grid;
  grid-template-columns: 8px auto auto;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 999px;
  color: $success-color;
  background: var(--vp-success-bg);
  font-size: 12px;

  i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }

  span {
    color: $text-primary;
  }

  small {
    margin-left: 6px;
    padding-left: 12px;
    border-left: 1px solid $border-color;
    color: $text-secondary;
  }
}

.checkout-main {
  min-height: calc(100vh - 74px);
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(390px, 0.65fr);
  // 保留一条窄灰缝，避免白块之间隔得太远。
  gap: 12px;
  padding: 12px;
  background: $bg-color;
}

.capture-section,
.basket-section {
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: $surface-color;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: $shadow-sm;
}

.capture-section {
  padding: 28px 30px 32px;
}

.basket-section {
  padding: 28px 28px 24px;
}

.section-heading,
.basket-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 20px;

  > div {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  span {
    color: $primary-color;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  h1,
  h2 {
    margin: 0;
    color: $text-primary;
    font-size: 23px;
    letter-spacing: -0.02em;
  }
}

.basket-heading {
  margin-bottom: 14px;

  .item-count-pill {
    min-width: 42px;
    padding: 6px 8px;
    border-radius: 999px;
    color: $primary-color;
    background: $primary-soft;
    text-align: center;
    font-size: 12px;
  }
}

.reset-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  color: $text-secondary;
  background: $surface-color;
  cursor: pointer;
  font-size: 12px;
  transition:
    border-color 0.2s,
    color 0.2s,
    background 0.2s;

  &:hover {
    border-color: $primary-color;
    color: $primary-color;
    background: $primary-soft;
  }
}

.source-tabs {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  margin-bottom: 12px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  overflow: hidden;
  background: $surface-color;

  button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    min-width: 150px;
    height: 40px;
    border: 0;
    border-right: 1px solid $border-color;
    color: $text-secondary;
    background: $surface-color;
    cursor: pointer;
    font-size: 13px;
    transition:
      color 0.2s,
      background 0.2s;

    &:last-child {
      border-right: 0;
    }

    &.active {
      color: #fff;
      background: $primary-color;
    }
  }
}

.camera-stage,
.upload-stage {
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  overflow: hidden;
}

.upload-stage {
  min-height: 440px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border-style: dashed;
  color: $text-secondary;

  > .el-icon {
    font-size: 40px;
    color: $primary-color;
  }

  strong {
    color: $text-primary;
    font-size: 15px;
  }

  span {
    font-size: 11px;
  }

  button {
    margin-top: 8px;
    padding: 9px 18px;
    border: 0;
    border-radius: $border-radius-sm;
    color: #fff;
    background: $primary-color;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.2s;

    &:hover {
      background: $primary-hover;
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.58;
    }
  }

  img {
    max-width: 90%;
    max-height: 350px;
    object-fit: contain;
  }
}

.upload-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;

  button.secondary {
    border: 1px solid $border-color;
    color: $text-primary;
    background: $surface-color;

    &:hover:not(:disabled) {
      border-color: $primary-color;
      color: $primary-color;
      background: $primary-soft;
    }
  }

  button.primary:hover:not(:disabled) {
    background: $primary-hover;
  }
}

.capture-footer {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin-top: 14px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-color;
  overflow: hidden;

  div {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 13px 15px;
    border-right: 1px solid $border-color;

    &:last-child {
      border-right: 0;
    }
  }

  span {
    color: $text-secondary;
    font-size: 10px;
  }

  strong {
    color: $text-primary;
    font-size: 14px;
  }

  .status-pill {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 22px;
    padding: 0 9px;
    border-radius: 999px;
    color: $primary-color;
    background: $primary-soft;
    font-size: 12px;
    font-weight: 600;

    &::before {
      content: '';
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }
  }
}

.price-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 11px;
  border-left: 3px solid $warning-color;
  border-radius: 0 $border-radius-sm $border-radius-sm 0;
  color: $text-primary;
  background: var(--vp-warning-bg);
  font-size: 11px;
  line-height: 1.55;

  .el-icon {
    margin-top: 2px;
    flex-shrink: 0;
    color: $warning-color;
  }
}

.product-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  margin: 15px -5px 15px 0;
  padding-right: 5px;
}

.product-item {
  position: relative;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) auto 27px;
  align-items: center;
  gap: 11px;
  padding: 13px 0;
  border-bottom: 1px solid $border-color;

  &:last-child {
    border-bottom: 0;
  }
}

.product-thumb {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  color: $primary-color;
  background: $primary-soft;
  font-size: 10px;
  font-weight: 800;
}

.product-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: $text-primary;
    font-size: 13px;
  }

  span {
    color: $text-secondary;
    font-size: 10px;
  }

  b {
    color: $warning-color;
    font-size: 11px;
  }
}

.quantity-control {
  display: grid;
  grid-template-columns: 26px 30px 26px;
  align-items: center;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  overflow: hidden;
  background: $surface-color;

  button {
    height: 28px;
    border: 0;
    color: $text-secondary;
    background: $surface-muted;
    cursor: pointer;
    transition:
      color 0.2s,
      background 0.2s;

    &:hover:not(:disabled) {
      color: $primary-color;
      background: $primary-soft;
    }

    &:disabled {
      color: $text-placeholder;
      cursor: not-allowed;
    }
  }

  span {
    text-align: center;
    color: $text-primary;
    font-size: 12px;
    font-weight: 800;
  }
}

.remove-button {
  width: 27px;
  height: 27px;
  border: 0;
  color: $text-secondary;
  background: transparent;
  cursor: pointer;
  transition: color 0.2s;

  &:hover {
    color: $danger-color;
  }
}

.empty-basket {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: $text-secondary;
  text-align: center;

  .el-icon {
    font-size: 44px;
    color: $text-placeholder;
  }

  strong {
    color: $text-primary;
    font-size: 15px;
  }

  span {
    font-size: 12px;
  }
}

.settlement-panel {
  padding-top: 18px;
  border-top: 1px solid $border-color;
}

.settlement-summary {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  margin-bottom: 14px;

  span {
    color: $text-secondary;
    font-size: 13px;
  }

  strong {
    grid-row: span 2;
    color: $text-primary;
    font-size: 28px;
  }

  small {
    color: $warning-color;
    font-size: 10px;
  }
}

.settlement-panel > button {
  width: 100%;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 0;
  border-radius: $border-radius-sm;
  color: #fff;
  background: $primary-color;
  cursor: pointer;
  font-size: 15px;
  font-weight: 800;
  transition: background 0.2s;

  &:hover {
    background: $primary-hover;
  }

  &:disabled {
    background: $text-placeholder;
    cursor: not-allowed;
  }
}

.settlement-panel p {
  margin: 9px 0 0;
  color: $text-secondary;
  text-align: center;
  font-size: 10px;
}

@media (max-width: 1050px) {
  .checkout-main {
    grid-template-columns: 1fr;
  }

  .basket-section {
    min-height: 620px;
  }
}

@media (max-width: 640px) {
  .checkout-header {
    height: 66px;
    padding: 0 16px;
  }

  .header-status small {
    display: none;
  }

  .checkout-main {
    min-height: calc(100vh - 66px);
    padding: 10px;
    gap: 10px;
  }

  .capture-section,
  .basket-section {
    padding: 20px 16px;
  }

  .section-heading h1,
  .basket-heading h2 {
    font-size: 20px;
  }

  .source-tabs {
    width: 100%;
  }

  .source-tabs button {
    min-width: 0;
  }

  .capture-footer {
    grid-template-columns: 1fr;
  }

  .capture-footer div {
    border-right: 0;
    border-bottom: 1px solid $border-color;
  }

  .capture-footer div:last-child {
    border-bottom: 0;
  }

  .product-item {
    grid-template-columns: 48px minmax(0, 1fr) 27px;
  }

  .product-thumb {
    width: 48px;
    height: 48px;
  }

  .quantity-control {
    grid-column: 2 / 3;
    justify-self: start;
  }

  .remove-button {
    grid-column: 3;
    grid-row: 1;
  }
}
</style>
