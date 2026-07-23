<template>
  <div class="mock-pay-page">
    <header class="mobile-header">
      <div class="brand">
        <span><img :src="faviconUrl" alt="VisionPay" /></span><strong>VisionPay</strong>
      </div>
      <span class="demo-badge">模拟支付</span>
    </header>

    <main class="mobile-main" aria-live="polite">
      <section v-if="loading" class="state-panel">
        <el-icon class="spin"><Loading /></el-icon>
        <h1>正在读取订单</h1>
      </section>

      <section v-else-if="loadError" class="state-panel error-state">
        <el-icon><Warning /></el-icon>
        <h1>{{ loadError }}</h1>
        <p>请返回收银端重新生成二维码。</p>
      </section>

      <section v-else-if="order.status === 'paid'" class="state-panel success-state">
        <span class="success-badge">
          <svg class="success-svg" viewBox="0 0 52 52" aria-hidden="true">
            <circle class="success-ring" cx="26" cy="26" r="23" />
            <path class="success-tick" pathLength="1" d="M16 27l7 7 13-14" />
          </svg>
        </span>
        <small>PAYMENT COMPLETE</small>
        <h1>模拟付款成功</h1>
        <strong>{{ formatMoney(order.amount) }}</strong>
        <p>收银端将在数秒内自动同步结果。</p>
        <div class="sync-progress" aria-hidden="true"><span></span></div>
        <div class="success-order">
          <span>订单编号</span><b>{{ orderNumber }}</b>
        </div>
      </section>

      <section v-else-if="order.status === 'expired'" class="state-panel error-state">
        <el-icon><Clock /></el-icon>
        <h1>二维码已过期</h1>
        <p>请返回收银端重新生成支付二维码。</p>
      </section>

      <section v-else class="payment-shell card-container">
        <div class="amount-section">
          <small>待支付金额</small><strong class="vp-num">{{ formatMoney(order.amount) }}</strong
          ><span>{{ countdownText }} 后二维码失效</span>
        </div>

        <div class="order-section">
          <div class="section-title">
            <h1>订单明细</h1>
            <span>{{ order.item_count }} 件商品</span>
          </div>
          <article v-for="item in order.items" :key="item.class_id">
            <div>
              <strong>{{ itemName(item) }}</strong
              ><span>{{ formatMoney(item.unit_price) }} x {{ item.count }}</span>
            </div>
            <b>{{ formatMoney(item.subtotal) }}</b>
          </article>
          <div class="order-number">
            <span>订单编号</span><b>{{ orderNumber }}</b>
          </div>
        </div>

        <fieldset class="method-section">
          <legend>选择模拟支付方式</legend>
          <div>
            <button
              type="button"
              class="method-wechat"
              :class="{ active: paymentMethod === 'wechat' }"
              :aria-pressed="paymentMethod === 'wechat'"
              @click="paymentMethod = 'wechat'"
            >
              <span class="method-icon"
                ><el-icon><ChatDotRound /></el-icon></span
              ><span>微信支付</span
              ><i
                ><el-icon v-if="paymentMethod === 'wechat'"><Check /></el-icon
              ></i>
            </button>
            <button
              type="button"
              class="method-alipay"
              :class="{ active: paymentMethod === 'alipay' }"
              :aria-pressed="paymentMethod === 'alipay'"
              @click="paymentMethod = 'alipay'"
            >
              <span class="method-icon"
                ><el-icon><Wallet /></el-icon></span
              ><span>支付宝</span
              ><i
                ><el-icon v-if="paymentMethod === 'alipay'"><Check /></el-icon
              ></i>
            </button>
          </div>
        </fieldset>

        <div v-if="confirmError" class="confirm-error" role="alert">{{ confirmError }}</div>
        <div class="confirm-bar">
          <button
            class="confirm-button"
            type="button"
            :disabled="submitting"
            @click="confirmPayment"
          >
            <el-icon v-if="submitting" class="spin"><Loading /></el-icon
            >{{ submitting ? '正在确认' : `确认模拟支付 ${formatMoney(order.amount)}` }}
          </button>
        </div>
        <p class="simulation-note">
          <el-icon><InfoFilled /></el-icon>演示环境不会调用真实支付渠道，也不会产生资金交易。
        </p>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Check,
  Clock,
  InfoFilled,
  Loading,
  Wallet,
  Warning,
} from '@element-plus/icons-vue'
import { confirmMockPaymentApi, getMockPaymentOrderApi } from '@/api/checkout'
import { notifyVisionPetPaymentSuccess, notifyVisionPetTask } from '@/utils/visionPet'

const route = useRoute()
const faviconUrl = '/favicon.svg'
const order = ref(null)
const loading = ref(true)
const submitting = ref(false)
const loadError = ref('')
const confirmError = ref('')
const paymentMethod = ref('wechat')
const now = ref(Date.now())
let countdownTimer = null

const orderNumber = computed(() =>
  order.value ? `VP-${order.value.order_uuid.slice(0, 8).toUpperCase()}` : '--',
)
const remainingSeconds = computed(() =>
  Math.max(0, Math.ceil((new Date(order.value?.expires_at || 0).getTime() - now.value) / 1000)),
)
const countdownText = computed(
  () =>
    `${String(Math.floor(remainingSeconds.value / 60)).padStart(2, '0')}:${String(remainingSeconds.value % 60).padStart(2, '0')}`,
)

function formatMoney(value) {
  return `¥ ${Number(value || 0).toFixed(2)}`
}
function itemName(item) {
  return item.name || item.sku_name || item.class_name || `商品 ${item.class_id}`
}

async function loadOrder() {
  loading.value = true
  loadError.value = ''
  try {
    order.value = await getMockPaymentOrderApi(route.params.token)
    if (order.value.status === 'pending')
      countdownTimer = window.setInterval(() => {
        now.value = Date.now()
      }, 1000)
  } catch (error) {
    loadError.value = error.response?.status === 404 ? '支付订单不存在' : '暂时无法读取订单'
  } finally {
    loading.value = false
  }
}

async function confirmPayment() {
  if (submitting.value) return
  submitting.value = true
  confirmError.value = ''
  notifyVisionPetTask({ state: 'working', message: '正在确认支付', duration: 0 })
  try {
    order.value = await confirmMockPaymentApi(route.params.token, paymentMethod.value)
    window.clearInterval(countdownTimer)
    if (order.value.status === 'paid') {
      notifyVisionPetPaymentSuccess({ amount: order.value.amount })
    } else {
      notifyVisionPetTask({ state: 'idle', message: '支付状态已更新', duration: 3200 })
    }
  } catch (error) {
    if (error.response?.status === 410) {
      order.value = { ...order.value, status: 'expired' }
      notifyVisionPetTask({ state: 'idle', message: '支付二维码已过期', duration: 4200 })
    } else {
      confirmError.value = '付款确认失败，请检查网络后重试。'
      notifyVisionPetTask({ state: 'error', message: '支付确认失败，请重试', duration: 5200 })
    }
  } finally {
    submitting.value = false
  }
}

onMounted(loadOrder)
onBeforeUnmount(() => window.clearInterval(countdownTimer))
</script>

<style lang="scss" scoped>
.mock-pay-page {
  min-height: 100vh;
  min-height: 100dvh;
  color: $text-primary;
  background: $bg-color;
}

.mobile-header {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: env(safe-area-inset-top) 18px 0;
  border-bottom: 1px solid $border-color;
  background: $surface-color;
  box-shadow: $shadow-sm;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;

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
    font-size: 17px;
  }
}

.demo-badge {
  padding: 6px 9px;
  border-radius: 999px;
  color: $warning-color;
  background: var(--vp-warning-bg);
  font-size: 12px;
  font-weight: 700;
}

.mobile-main {
  width: min(100% - 24px, 480px);
  margin: 0 auto;
  padding: 20px 0 calc(28px + env(safe-area-inset-bottom));
}

.payment-shell {
  padding: 0;
  overflow: hidden;
}

.amount-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 12px 12px 0;
  padding: 26px 20px 24px;
  border-radius: $border-radius-lg;
  background: var(--vp-brand-gradient);

  html.dark & {
    box-shadow: var(--vp-glow-primary);
  }

  small {
    color: rgba(255, 255, 255, 0.8);
    font-size: 13px;
  }

  strong {
    margin: 5px 0 8px;
    color: #fff;
    font-family: var(--vp-font-mono);
    font-size: 38px;
  }

  span {
    color: rgba(255, 255, 255, 0.85);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
}

.order-section {
  padding: 20px;

  article {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 13px 0;
    border-bottom: 1px solid $border-color;

    &:last-of-type {
      border-bottom: 0;
    }

    > div {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    strong {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: $text-primary;
      font-size: 14px;
    }

    span {
      color: $text-secondary;
      font-size: 12px;
    }

    b {
      flex-shrink: 0;
      color: $warning-color;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }
  }
}

.section-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;

  h1 {
    margin: 0;
    color: $text-primary;
    font-size: 17px;
  }

  span {
    color: $text-secondary;
    font-size: 12px;
  }
}

.order-number {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  color: $text-secondary;
  font-size: 11px;

  b {
    color: $text-primary;
    font-family: var(--vp-font-mono);
  }
}

.method-section {
  margin: 0;
  padding: 0 20px 18px;
  border: 0;

  legend {
    width: 100%;
    padding: 0 0 10px;
    color: $text-primary;
    font-size: 14px;
    font-weight: 700;
  }

  > div {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  button {
    min-height: 64px;
    display: grid;
    grid-template-columns: 40px 1fr 20px;
    align-items: center;
    gap: 10px;
    padding: 0 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    color: $text-primary;
    background: $surface-color;
    cursor: pointer;
    font-size: 13px;
    font-weight: 700;
    transition:
      border-color 0.2s,
      color 0.2s,
      background 0.2s,
      box-shadow 0.2s;

    &.method-wechat {
      --method-brand: #07c160;
    }

    &.method-alipay {
      --method-brand: #1677ff;
    }

    &.active {
      border-color: var(--method-brand);
      box-shadow: inset 0 0 0 1px var(--method-brand);
      background: color-mix(in srgb, var(--method-brand) 6%, $surface-color);
    }

    .method-icon {
      width: 40px;
      height: 40px;
      display: grid;
      place-items: center;
      border-radius: 10px;
      color: var(--method-brand);
      background: color-mix(in srgb, var(--method-brand) 12%, transparent);
      transition:
        color 0.2s,
        background 0.2s;

      .el-icon {
        font-size: 22px;
      }
    }

    &.active .method-icon {
      color: #fff;
      background: var(--method-brand);
    }

    i {
      width: 19px;
      height: 19px;
      display: grid;
      place-items: center;
      border: 1px solid $border-strong;
      border-radius: 50%;
      color: #fff;
    }

    &.active i {
      border-color: var(--method-brand);
      background: var(--method-brand);
    }
  }
}

.confirm-bar {
  padding: 0 20px;
}

.confirm-button {
  width: 100%;
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  border: 0;
  border-radius: $border-radius-sm;
  color: #fff;
  background: $primary-color;
  cursor: pointer;
  font-size: 15px;
  font-weight: 800;
  transition:
    background 0.2s,
    color 0.2s,
    transform 0.15s ease;

  &:active {
    background: $primary-hover;
    transform: scale(0.98);
  }

  &:disabled {
    color: $text-secondary;
    background: $surface-muted;
    cursor: not-allowed;
  }
}

.confirm-error {
  margin: 0 20px 12px;
  padding: 10px 12px;
  border-radius: $border-radius-sm;
  color: $danger-color;
  background: var(--vp-danger-bg);
  font-size: 12px;
}

.simulation-note {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 6px;
  margin: 14px 20px 20px;
  color: $text-secondary;
  font-size: 11px;
  line-height: 1.5;

  .el-icon {
    flex-shrink: 0;
    margin-top: 1px;
  }
}

.state-panel {
  min-height: calc(100dvh - 120px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;

  > .el-icon {
    font-size: 48px;
    color: $primary-color;

    html.dark & {
      filter: drop-shadow(0 0 12px var(--vp-border-glow));
    }
  }

  h1 {
    margin: 15px 0 6px;
    color: $text-primary;
    font-size: 23px;
  }

  p {
    margin: 0;
    color: $text-secondary;
    font-size: 14px;
  }

  > small {
    margin-top: 18px;
    color: $success-color;
    font-size: 11px;
    font-weight: 800;
  }

  > strong {
    margin: 6px 0 8px;
    color: $text-primary;
    font-size: 36px;
    font-variant-numeric: tabular-nums;
  }
}

.success-badge {
  width: 80px;
  height: 80px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: $success-color;
  background: var(--vp-success-bg);
}

.success-svg {
  width: 46px;
  height: 46px;
}

.success-ring {
  fill: none;
  stroke: currentColor;
  stroke-width: 3.5;
}

.success-tick {
  fill: none;
  stroke: currentColor;
  stroke-width: 4.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sync-progress {
  width: 168px;
  height: 3px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: $surface-muted;

  span {
    display: block;
    width: 45%;
    height: 100%;
    border-radius: inherit;
    background: var(--vp-brand-gradient);
    transform: translateX(-100%);
  }
}

.success-order {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 22px;
  padding: 13px 14px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: $surface-color;
  color: $text-secondary;
  font-size: 12px;
  box-sizing: border-box;

  b {
    color: $text-primary;
    font-family: var(--vp-font-mono);
  }
}

.error-state > .el-icon {
  color: $warning-color;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: no-preference) {
  .success-ring {
    transform-box: fill-box;
    transform-origin: center;
    animation: success-ring-pop 0.55s $ease-vision-out both;
  }

  .success-tick {
    stroke-dasharray: 1;
    stroke-dashoffset: 1;
    animation: success-tick-draw 0.4s ease-out 0.4s forwards;
  }

  .sync-progress span {
    animation: sync-progress-slide 3.6s linear infinite;
  }
}

@keyframes success-ring-pop {
  0% {
    opacity: 0;
    transform: scale(0.3);
  }
  60% {
    opacity: 1;
    transform: scale(1.1);
  }
  100% {
    transform: scale(1);
  }
}

@keyframes success-tick-draw {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes sync-progress-slide {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(230%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}

@media (max-width: 370px) {
  .method-section > div {
    grid-template-columns: 1fr;
  }

  .amount-section strong {
    font-size: 34px;
  }
}
</style>
