<template>
  <div class="mock-pay-page">
    <header class="mobile-header">
      <div class="brand">
        <span><img src="/favicon.svg" alt="VisionPay" /></span><strong>VisionPay</strong>
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
        <span
          ><el-icon><CircleCheckFilled /></el-icon></span
        ><small>PAYMENT COMPLETE</small>
        <h1>模拟付款成功</h1>
        <strong>{{ formatMoney(order.amount) }}</strong>
        <p>收银端将在数秒内自动同步结果。</p>
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
          <small>待支付金额</small><strong>{{ formatMoney(order.amount) }}</strong
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
              :class="{ active: paymentMethod === 'wechat' }"
              :aria-pressed="paymentMethod === 'wechat'"
              @click="paymentMethod = 'wechat'"
            >
              <el-icon><ChatDotRound /></el-icon><span>微信支付</span
              ><i
                ><el-icon v-if="paymentMethod === 'wechat'"><Check /></el-icon
              ></i>
            </button>
            <button
              type="button"
              :class="{ active: paymentMethod === 'alipay' }"
              :aria-pressed="paymentMethod === 'alipay'"
              @click="paymentMethod = 'alipay'"
            >
              <el-icon><Wallet /></el-icon><span>支付宝</span
              ><i
                ><el-icon v-if="paymentMethod === 'alipay'"><Check /></el-icon
              ></i>
            </button>
          </div>
        </fieldset>

        <div v-if="confirmError" class="confirm-error" role="alert">{{ confirmError }}</div>
        <button class="confirm-button" type="button" :disabled="submitting" @click="confirmPayment">
          <el-icon v-if="submitting" class="spin"><Loading /></el-icon
          >{{ submitting ? '正在确认' : `确认模拟支付 ${formatMoney(order.amount)}` }}
        </button>
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
  CircleCheckFilled,
  Clock,
  InfoFilled,
  Loading,
  Wallet,
  Warning,
} from '@element-plus/icons-vue'
import { confirmMockPaymentApi, getMockPaymentOrderApi } from '@/api/checkout'

const route = useRoute()
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
  try {
    order.value = await confirmMockPaymentApi(route.params.token, paymentMethod.value)
    window.clearInterval(countdownTimer)
  } catch (error) {
    if (error.response?.status === 410) order.value = { ...order.value, status: 'expired' }
    else confirmError.value = '付款确认失败，请检查网络后重试。'
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
  padding: 28px 20px 24px;
  border-bottom: 1px solid $border-color;
  background: $surface-muted;

  small {
    color: $text-secondary;
    font-size: 13px;
  }

  strong {
    margin: 5px 0 8px;
    color: $text-primary;
    font-size: 38px;
    font-variant-numeric: tabular-nums;
  }

  span {
    color: $primary-color;
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
    font-family: ui-monospace, monospace;
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
    min-height: 56px;
    display: grid;
    grid-template-columns: 24px 1fr 20px;
    align-items: center;
    gap: 7px;
    padding: 0 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    color: $text-primary;
    background: $surface-color;
    cursor: pointer;
    transition:
      border-color 0.2s,
      color 0.2s,
      background 0.2s;

    &.active {
      border: 2px solid $primary-color;
      padding: 0 11px;
      color: $primary-color;
      background: $primary-soft;
    }

    > .el-icon {
      font-size: 20px;
    }

    span {
      font-size: 13px;
      font-weight: 700;
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
      border-color: $primary-color;
      background: $primary-color;
    }
  }
}

.confirm-button {
  width: calc(100% - 40px);
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 20px;
  border: 0;
  border-radius: $border-radius-sm;
  color: #fff;
  background: $primary-color;
  cursor: pointer;
  font-size: 15px;
  font-weight: 800;
  transition: background 0.2s;

  &:active {
    background: $primary-hover;
  }

  &:disabled {
    opacity: 0.62;
    cursor: wait;
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

  > span {
    width: 80px;
    height: 80px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: $success-color;
    background: var(--vp-success-bg);
    font-size: 52px;
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
    font-family: ui-monospace, monospace;
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
