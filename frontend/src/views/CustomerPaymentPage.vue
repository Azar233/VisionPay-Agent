<template>
  <div class="payment-page">
    <header class="payment-header">
      <button type="button" @click="router.push('/checkout')">
        <el-icon><ArrowLeft /></el-icon><span>返回商品确认</span>
      </button>
      <div class="brand">
        <span><img :src="faviconUrl" alt="VisionPay" /></span><strong>VisionPay 自助结算</strong>
      </div>
      <div class="secure-label">
        <el-icon><Lock /></el-icon>模拟支付环境
      </div>
    </header>

    <main class="payment-main">
      <div class="payment-steps" aria-label="结算进度">
        <div class="done">
          <span
            ><el-icon><Check /></el-icon></span
          ><b>扫描商品</b>
        </div>
        <i></i>
        <div class="done">
          <span
            ><el-icon><Check /></el-icon></span
          ><b>确认清单</b>
        </div>
        <i></i>
        <div :class="{ active: paymentStatus === 'pending', done: paymentStatus === 'paid' }">
          <span
            ><el-icon v-if="paymentStatus === 'paid'"><Check /></el-icon
            ><template v-else>3</template></span
          ><b>完成付款</b>
        </div>
      </div>

      <section v-if="!paymentOrder" class="empty-state card-container">
        <el-icon><Warning /></el-icon>
        <h1>没有可支付的订单</h1>
        <p>请返回结算页确认商品后重新创建订单。</p>
        <button type="button" @click="router.push('/checkout')">返回顾客结算端</button>
      </section>

      <section v-else class="payment-layout card-container">
        <aside class="order-panel">
          <div class="panel-heading">
            <span>订单摘要</span><small>{{ orderNumber }}</small>
          </div>
          <div class="order-items">
            <article v-for="item in paymentOrder.items" :key="item.class_id">
              <div class="item-mark">{{ itemMark(item) }}</div>
              <div>
                <strong>{{ itemName(item) }}</strong
                ><span>数量 x {{ item.count }}</span>
              </div>
              <b class="vp-num">{{ formatMoney(item.subtotal) }}</b>
            </article>
          </div>
          <div class="order-count">
            <span>商品总数</span><strong>{{ paymentOrder.item_count }} 件</strong>
          </div>
          <div class="order-total">
            <div><span>应付金额</span><small>金额由服务端商品价格生成</small></div>
            <strong class="vp-num">{{ formatMoney(paymentOrder.amount) }}</strong>
          </div>
          <dl class="order-meta">
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatDate(paymentOrder.created_at) }}</dd>
            </div>
            <div>
              <dt>支付状态</dt>
              <dd
                class="vp-pill"
                :class="{
                  'vp-pill--success': paymentStatus === 'paid',
                  'vp-pill--warning': paymentStatus === 'pending',
                  'vp-pill--danger': paymentStatus === 'expired',
                }"
              >
                {{ statusText }}
              </dd>
            </div>
          </dl>
        </aside>

        <section class="pay-panel" aria-live="polite">
          <div v-if="paymentStatus === 'paid'" class="result-state success-state">
            <span class="result-icon success-icon">
              <svg viewBox="0 0 76 76" fill="none" aria-hidden="true">
                <circle class="success-ring" cx="38" cy="38" r="30" />
                <path class="success-check" d="M25 39.5l9.5 9.5L51 29" />
              </svg>
            </span>
            <small>PAYMENT COMPLETE</small>
            <h1>付款成功</h1>
            <strong class="vp-num">{{ formatMoney(successAmount) }}</strong>
            <p>手机端确认结果已同步至当前收银端。</p>
            <div class="result-reference">
              <span>订单编号</span><b>{{ orderNumber }}</b>
            </div>
            <button type="button" @click="startNewCheckout">完成并开始新结算</button>
          </div>

          <div v-else-if="paymentStatus === 'expired'" class="result-state expired-state">
            <span class="result-icon"
              ><el-icon><Clock /></el-icon
            ></span>
            <small>QR CODE EXPIRED</small>
            <h1>支付二维码已过期</h1>
            <p>为避免订单串单，请生成新的支付二维码。</p>
            <button type="button" :disabled="regenerating" @click="regenerateOrder">
              {{ regenerating ? '正在生成' : '重新生成二维码' }}
            </button>
          </div>

          <template v-else>
            <div class="pay-heading">
              <div>
                <small>模拟扫码支付</small>
                <h1>请使用手机扫描二维码</h1>
              </div>
              <span class="vp-pill vp-pill--warning">等待付款</span>
            </div>

            <div class="qr-section">
              <div class="qr-stage">
                <svg class="qr-ring" viewBox="0 0 266 266" aria-hidden="true">
                  <circle class="qr-ring-track" cx="133" cy="133" r="129" />
                  <circle
                    class="qr-ring-progress"
                    cx="133"
                    cy="133"
                    r="129"
                    :stroke-dasharray="QR_RING_CIRCUMFERENCE"
                    :stroke-dashoffset="qrRingOffset"
                  />
                </svg>
                <div class="qr-frame">
                  <img
                    v-if="qrDataUrl"
                    :src="qrDataUrl"
                    width="220"
                    height="220"
                    alt="模拟支付二维码"
                  />
                  <el-icon v-else class="qr-loading"><Loading /></el-icon>
                  <i class="qr-scanline" aria-hidden="true"></i>
                </div>
              </div>
              <div class="qr-copy">
                <strong class="vp-num">{{ formatMoney(paymentOrder.amount) }}</strong>
                <span>手机与收银设备需连接同一局域网</span>
                <small>二维码有效期 {{ countdownText }}</small>
                <div class="url-chip">
                  <code ref="urlTextRef" :title="paymentUrl">{{ paymentUrl }}</code>
                  <button type="button" aria-label="复制支付链接" @click="copyPaymentUrl">
                    <el-icon><CopyDocument /></el-icon>
                  </button>
                </div>
              </div>
            </div>

            <div class="waiting-status">
              <el-icon><Loading /></el-icon>
              <div>
                <strong>正在等待手机端确认</strong><span>页面将自动同步支付结果，无需手动刷新</span>
              </div>
            </div>
            <a class="test-link" :href="localPaymentUrl" target="_blank" rel="noopener"
              >在本机打开测试付款页</a
            >
            <p class="simulation-note">
              <el-icon><InfoFilled /></el-icon
              >本功能仅模拟支付状态，不会调用微信、支付宝或产生真实资金交易。
            </p>
          </template>
        </section>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Check,
  Clock,
  CopyDocument,
  InfoFilled,
  Loading,
  Lock,
  Warning,
} from '@element-plus/icons-vue'
import {
  createMockPaymentOrderApi,
  getMockPaymentOrderApi,
  getMockPaymentStatusApi,
} from '@/api/checkout'
import { notifyVisionPetPaymentSuccess, notifyVisionPetTask } from '@/utils/visionPet'
import { useCountUp } from '@/composables/useCountUp'

const router = useRouter()
const route = useRoute()
const faviconUrl = '/favicon.svg'
const paymentOrder = ref(loadSession('visionpay-payment-order'))
const cartOrder = ref(loadSession('visionpay-checkout-order'))
const qrDataUrl = ref('')
const now = ref(Date.now())
const polling = ref(false)
const regenerating = ref(false)
let statusTimer = null
let countdownTimer = null
let paymentSuccessAnnounced = false

const paymentStatus = computed(() => paymentOrder.value?.status || '')
const statusText = computed(
  () =>
    ({ pending: '等待付款', paid: '付款成功', expired: '已过期' })[paymentStatus.value] || '未知',
)
const orderNumber = computed(() =>
  paymentOrder.value ? `VP-${paymentOrder.value.order_uuid.slice(0, 8).toUpperCase()}` : '--',
)
const paymentPath = computed(() =>
  paymentOrder.value ? `/mock-pay/${paymentOrder.value.payment_token}` : '',
)
const publicOrigin = (
  import.meta.env.VITE_CHECKOUT_PUBLIC_ORIGIN || window.location.origin
).replace(/\/$/, '')
const paymentUrl = computed(() => `${publicOrigin}${paymentPath.value}`)
const localPaymentUrl = computed(() => `${window.location.origin}${paymentPath.value}`)
const remainingSeconds = computed(() =>
  Math.max(
    0,
    Math.ceil((new Date(paymentOrder.value?.expires_at || 0).getTime() - now.value) / 1000),
  ),
)
const countdownText = computed(
  () =>
    `${String(Math.floor(remainingSeconds.value / 60)).padStart(2, '0')}:${String(remainingSeconds.value % 60).padStart(2, '0')}`,
)

// 环形倒计时：复用 remainingSeconds（由现有 countdownTimer 驱动），按订单有效期换算进度。
const QR_RING_RADIUS = 129
const QR_RING_CIRCUMFERENCE = 2 * Math.PI * QR_RING_RADIUS
const countdownTotalSeconds = computed(() => {
  const total = Math.round(
    (new Date(paymentOrder.value?.expires_at || 0).getTime() -
      new Date(paymentOrder.value?.created_at || 0).getTime()) /
      1000,
  )
  return total > 0 ? total : remainingSeconds.value || 1
})
const qrRingOffset = computed(() => {
  const progress = Math.min(1, Math.max(0, remainingSeconds.value / countdownTotalSeconds.value))
  return QR_RING_CIRCUMFERENCE * (1 - progress)
})

// 成功态金额滚动动画：未支付时停在 0，变为 paid 后滚到订单金额。
const successAmount = useCountUp(
  () => (paymentStatus.value === 'paid' ? Number(paymentOrder.value?.amount) || 0 : 0),
  { duration: 900 },
)

const urlTextRef = ref(null)

async function copyPaymentUrl() {
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(paymentUrl.value)
    ElMessage.success('支付链接已复制，可粘贴到手机浏览器打开')
  } catch {
    selectPaymentUrlText()
    ElMessage.warning('无法访问剪贴板，已为你选中链接，请手动复制')
  }
}

function selectPaymentUrlText() {
  if (!urlTextRef.value) return
  const selection = window.getSelection()
  const range = document.createRange()
  range.selectNodeContents(urlTextRef.value)
  selection.removeAllRanges()
  selection.addRange(range)
}

function loadSession(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key)) || null
  } catch {
    return null
  }
}
function formatMoney(value) {
  return `¥ ${Number(value || 0).toFixed(2)}`
}
function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
}
function itemName(item) {
  return item.name || item.sku_name || item.class_name || `商品 ${item.class_id}`
}
function itemMark(item) {
  return itemName(item).slice(0, 2).toUpperCase()
}

async function renderQrCode() {
  if (!paymentPath.value) return
  qrDataUrl.value = await QRCode.toDataURL(paymentUrl.value, {
    width: 440,
    margin: 2,
    errorCorrectionLevel: 'M',
    color: { dark: '#111827', light: '#ffffff' },
  })
}

async function pollStatus() {
  if (!paymentOrder.value || polling.value || paymentStatus.value !== 'pending') return
  polling.value = true
  try {
    const previousStatus = paymentStatus.value
    const status = await getMockPaymentStatusApi(paymentOrder.value.order_uuid)
    paymentOrder.value = { ...paymentOrder.value, ...status }
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder.value))
    if (previousStatus !== 'paid' && status.status === 'paid') announcePaymentSuccess()
    if (status.status !== 'pending') stopTimers()
  } catch {
    // Keep the current state and retry on the next interval.
  } finally {
    polling.value = false
  }
}

function announcePaymentSuccess() {
  if (paymentSuccessAnnounced || paymentStatus.value !== 'paid') return
  paymentSuccessAnnounced = true
  notifyVisionPetPaymentSuccess({ amount: paymentOrder.value?.amount })
}

function startTimers() {
  stopTimers()
  countdownTimer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  statusTimer = window.setInterval(pollStatus, 1000)
}
function stopTimers() {
  window.clearInterval(statusTimer)
  window.clearInterval(countdownTimer)
  statusTimer = null
  countdownTimer = null
}

async function regenerateOrder() {
  if (!cartOrder.value?.items?.length) return router.push('/checkout')
  regenerating.value = true
  try {
    paymentSuccessAnnounced = false
    paymentOrder.value = await createMockPaymentOrderApi(
      cartOrder.value.items,
      cartOrder.value.modelVersionId || null,
    )
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder.value))
    router.replace({
      path: '/checkout/payment',
      query: { token: paymentOrder.value.payment_token },
    })
    now.value = Date.now()
    await renderQrCode()
    startTimers()
  } finally {
    regenerating.value = false
  }
}

function startNewCheckout() {
  notifyVisionPetTask({ state: 'idle', message: '', duration: 0 })
  sessionStorage.removeItem('visionpay-payment-order')
  sessionStorage.removeItem('visionpay-checkout-order')
  router.push('/checkout')
}

onMounted(async () => {
  const routeToken = typeof route.query.token === 'string' ? route.query.token : ''
  if (routeToken && paymentOrder.value?.payment_token !== routeToken) {
    try {
      const restoredOrder = await getMockPaymentOrderApi(routeToken)
      paymentOrder.value = { ...restoredOrder, payment_token: routeToken }
      sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder.value))
    } catch {
      paymentOrder.value = null
    }
  }
  if (!paymentOrder.value) return
  await renderQrCode()
  if (paymentStatus.value === 'paid') announcePaymentSuccess()
  if (paymentStatus.value === 'pending') {
    await pollStatus()
    if (paymentStatus.value === 'pending') startTimers()
  }
})
onBeforeUnmount(stopTimers)
</script>

<style lang="scss" scoped>
.payment-page {
  min-height: 100vh;
  color: $text-primary;
  background: $bg-color;
}

.payment-header {
  height: 72px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 32px;
  border-bottom: 1px solid $border-color;
  background: $surface-color;
  box-shadow: $shadow-sm;

  > button {
    min-height: 44px;
    justify-self: start;
    display: flex;
    align-items: center;
    gap: 7px;
    border: 0;
    color: $text-secondary;
    background: transparent;
    cursor: pointer;
    font-size: 14px;
    transition: color 0.2s;

    &:hover {
      color: $primary-color;
    }
  }
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;

  > span {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: $border-radius-sm;
    background: $primary-color;
  }

  img {
    width: 20px;
    filter: brightness(0) invert(1);
  }

  strong {
    color: $text-primary;
    font-size: 16px;
  }
}

.secure-label {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  color: $success-color;
  background: var(--vp-success-bg);
  font-size: 12px;
}

.payment-main {
  width: min(1120px, calc(100% - 40px));
  margin: 0 auto;
  padding: 26px 0 44px;
}

.payment-steps {
  width: min(570px, 100%);
  display: grid;
  grid-template-columns: auto 1fr auto 1fr auto;
  align-items: center;
  margin: 0 auto 26px;

  > i {
    height: 1px;
    background: $border-strong;
  }

  > div {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    color: $text-secondary;
    font-size: 11px;
  }

  span {
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border: 1px solid $border-strong;
    border-radius: 50%;
    background: $surface-color;
    font-size: 12px;
  }

  .done {
    color: $success-color;

    span {
      border-color: $success-color;
      color: #fff;
      background: $success-color;
    }
  }

  .active {
    color: $primary-color;

    span {
      border: 2px solid $primary-color;
      color: $primary-color;
      font-weight: 800;
    }
  }
}

.payment-layout {
  display: grid;
  grid-template-columns: minmax(320px, 0.78fr) minmax(460px, 1.22fr);
  padding: 0;
  overflow: hidden;
}

.order-panel,
.pay-panel {
  min-width: 0;
  padding: 28px;
}

.order-panel {
  border-right: 1px solid $border-color;
  background: $surface-muted;
}

.panel-heading,
.order-count {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading {
  align-items: baseline;
  margin-bottom: 16px;

  > span {
    color: $text-primary;
    font-size: 18px;
    font-weight: 700;
  }

  small {
    color: $text-secondary;
    font-size: 11px;
    font-family: ui-monospace, monospace;
  }
}

.order-items article {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  padding: 13px 0;
  border-bottom: 1px solid $border-color;

  &:last-child {
    border-bottom: 0;
  }
}

.item-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  color: $primary-color;
  background: $primary-soft;
  font-size: 10px;
  font-weight: 800;
}

.order-items article > div:nth-child(2) {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.order-items strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: $text-primary;
  font-size: 13px;
}

.order-items span {
  color: $text-secondary;
  font-size: 11px;
}

.order-items b {
  color: $text-primary;
  font-size: 12px;
  text-align: right;
}

.order-count {
  padding: 14px 0;
  color: $text-secondary;
  font-size: 12px;
}

.order-total {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  padding: 17px 0;
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;

  > div {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  span {
    color: $text-primary;
    font-size: 14px;
    font-weight: 700;
  }

  small {
    color: $text-secondary;
    font-size: 10px;
  }

  > strong {
    color: $text-primary;
    font-size: 28px;
    text-align: right;
  }
}

.order-meta {
  margin: 14px 0 0;

  > div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 5px 0;
    color: $text-secondary;
    font-size: 11px;
  }

  dd {
    margin: 0;
  }
}

.pay-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;

  > div {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  small {
    color: $primary-color;
    font-size: 10px;
    font-weight: 800;
  }

  h1 {
    margin: 0;
    color: $text-primary;
    font-size: 21px;
  }
}

.qr-section {
  min-height: 288px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 28px;
  margin-top: 20px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-muted;

  html.dark & {
    border-color: var(--vp-border-glow);
    background:
      radial-gradient(130% 120% at 50% -10%, var(--vp-aurora-1), transparent 62%),
      var(--vp-surface-muted);
  }
}

.qr-stage {
  position: relative;
  display: grid;
}

.qr-ring {
  position: absolute;
  top: -12px;
  left: -12px;
  width: 266px;
  height: 266px;
  pointer-events: none;

  circle {
    fill: none;
  }
}

.qr-ring-track {
  stroke: $border-color;
  stroke-width: 3;
}

.qr-ring-progress {
  stroke: var(--vp-accent-cyan);
  stroke-width: 3;
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: center;
  transition: stroke-dashoffset 1s linear;

  html.dark & {
    filter: drop-shadow(0 0 4px var(--vp-accent-cyan));
  }
}

.qr-frame {
  position: relative;
  width: 242px;
  height: 242px;
  display: grid;
  place-items: center;
  padding: 10px;
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: #ffffff;

  img {
    display: block;
    width: 220px;
    height: 220px;
  }
}

.qr-scanline {
  position: absolute;
  top: 7px;
  left: 7px;
  right: 7px;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, transparent, var(--vp-accent-cyan), transparent);
  opacity: 0;
  pointer-events: none;
}

.qr-loading {
  font-size: 32px;
  color: $primary-color;
  animation: spin 1s linear infinite;
}

.qr-copy {
  min-width: 0;
  max-width: 230px;
  display: flex;
  flex-direction: column;
  gap: 9px;

  strong {
    color: $text-primary;
    font-size: 30px;
  }

  span {
    color: $text-secondary;
    font-size: 12px;
  }

  small {
    color: $primary-color;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
}

.url-chip {
  max-width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 5px 5px 10px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-color;
  transition: border-color 0.2s;

  &:hover {
    border-color: var(--vp-border-glow);
  }

  html.dark & {
    background: rgba(255, 255, 255, 0.05);
  }

  code {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: $text-secondary;
    font-family: var(--vp-font-mono);
    font-size: 11px;
    line-height: 1.45;
  }

  button {
    flex-shrink: 0;
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border: 0;
    border-radius: 6px;
    color: $primary-color;
    background: $primary-soft;
    cursor: pointer;
    transition:
      color 0.2s,
      background 0.2s;

    &:hover {
      color: #fff;
      background: $primary-color;
    }
  }
}

.waiting-status {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: $border-radius-sm;
  color: $text-primary;
  background: $primary-soft;

  > .el-icon {
    flex-shrink: 0;
    color: $primary-color;
    animation: spin 1s linear infinite;
  }

  > div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  strong {
    font-size: 12px;
  }

  span {
    color: $text-secondary;
    font-size: 10px;
  }
}

.test-link {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 12px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  color: $primary-color;
  text-decoration: none;
  font-size: 12px;
  font-weight: 700;
  transition:
    border-color 0.2s,
    background 0.2s;

  &:hover {
    border-color: $primary-color;
    background: $primary-soft;
  }
}

.simulation-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 12px 0 0;
  color: $text-secondary;
  font-size: 10px;
  line-height: 1.5;

  .el-icon {
    flex-shrink: 0;
    margin-top: 1px;
  }
}

.result-state {
  min-height: 480px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.result-icon {
  width: 76px;
  height: 76px;
  display: grid;
  place-items: center;
  margin-bottom: 18px;
  border-radius: 50%;
  font-size: 48px;
}

.result-state > small {
  color: $text-secondary;
  font-size: 10px;
  font-weight: 800;
}

.result-state h1 {
  margin: 6px 0;
  color: $text-primary;
  font-size: 28px;
}

.result-state > strong {
  margin: 4px 0 8px;
  color: $text-primary;
  font-family: var(--vp-font-mono);
  font-size: 34px;
  letter-spacing: -0.02em;
}

.result-state p {
  margin: 0 0 22px;
  color: $text-secondary;
  font-size: 12px;
}

.result-state > button,
.empty-state button {
  min-width: 230px;
  min-height: 48px;
  border: 0;
  border-radius: $border-radius-sm;
  color: #fff;
  background: $primary-color;
  cursor: pointer;
  font-weight: 800;
  transition: background 0.2s;

  &:hover {
    background: $primary-hover;
  }

  &:disabled {
    opacity: 0.55;
    cursor: wait;
  }
}

.success-state .result-icon {
  color: $success-color;
  background: var(--vp-success-bg);

  html.dark & {
    box-shadow: 0 0 32px rgba(52, 211, 153, 0.25);
  }
}

.success-icon svg {
  width: 42px;
  height: 42px;
}

.success-ring {
  stroke: currentColor;
  stroke-width: 4;
}

.success-check {
  stroke: currentColor;
  stroke-width: 5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.expired-state .result-icon {
  color: $warning-color;
  background: var(--vp-warning-bg);
}

.result-reference {
  width: min(330px, 100%);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 22px;
  padding: 12px;
  border-radius: $border-radius-sm;
  background: $surface-muted;
  color: $text-secondary;
  font-size: 11px;

  b {
    color: $text-primary;
    font-family: ui-monospace, monospace;
  }
}

.empty-state {
  min-height: 430px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;

  > .el-icon {
    font-size: 48px;
    color: $warning-color;
  }

  h1 {
    margin: 15px 0 6px;
    color: $text-primary;
  }

  p {
    margin: 0 0 20px;
    color: $text-secondary;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes qr-pulse {
  0% {
    box-shadow:
      0 0 0 0 var(--vp-border-glow),
      var(--vp-glow-primary);
  }
  100% {
    box-shadow:
      0 0 0 18px rgba(0, 0, 0, 0),
      var(--vp-glow-primary);
  }
}

@keyframes qr-scan {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(224px);
  }
}

@keyframes success-pop {
  0% {
    opacity: 0;
    transform: scale(0.4);
  }
  60% {
    opacity: 1;
    transform: scale(1.08);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes success-draw {
  to {
    stroke-dashoffset: 0;
  }
}

@media (prefers-reduced-motion: no-preference) {
  .qr-frame {
    animation: qr-pulse 2.4s ease-out infinite;
  }

  .qr-scanline {
    opacity: 0.45;
    animation: qr-scan 3s ease-in-out infinite alternate;
  }

  .success-state .result-icon {
    animation: success-pop 0.55s var(--vp-ease-vision-out) both;
  }

  .success-check {
    stroke-dasharray: 42;
    stroke-dashoffset: 42;
    animation: success-draw 0.4s ease-out 0.35s forwards;
  }
}

@media (prefers-reduced-motion: reduce) {
  .qr-loading,
  .waiting-status > .el-icon {
    animation: none;
  }
}

@media (max-width: 900px) {
  .payment-header {
    grid-template-columns: 1fr auto;
    padding: 0 18px;
  }

  .payment-header .brand {
    display: none;
  }

  .payment-layout {
    grid-template-columns: 1fr;
  }

  .order-panel {
    border-right: 0;
    border-bottom: 1px solid $border-color;
  }

  .payment-main {
    width: min(100% - 24px, 680px);
  }

  .qr-section {
    padding: 24px;
  }
}

@media (max-width: 560px) {
  .payment-header > button span,
  .secure-label {
    display: none;
  }

  .payment-main {
    width: calc(100% - 20px);
    padding-top: 18px;
  }

  .payment-steps b {
    display: none;
  }

  .order-panel,
  .pay-panel {
    padding: 20px 16px;
  }

  .qr-section {
    flex-direction: column;
    gap: 16px;
    text-align: center;
  }

  .qr-copy {
    align-items: center;
  }

  .pay-heading {
    align-items: center;
  }

  .pay-heading h1 {
    font-size: 18px;
  }

  .pay-heading > span {
    flex-shrink: 0;
  }

  .qr-frame {
    width: 232px;
    height: 232px;
  }

  .qr-ring {
    width: 256px;
    height: 256px;
  }

  .qr-frame img {
    width: 210px;
    height: 210px;
  }
}
</style>
