<template>
  <div class="payment-page">
    <header class="payment-header">
      <button type="button" @click="router.push('/checkout')">
        <el-icon><ArrowLeft /></el-icon><span>返回商品确认</span>
      </button>
      <div class="brand"><span><img src="/favicon.svg" alt="VisionPay" /></span><strong>VisionPay 自助结算</strong></div>
      <div class="secure-label"><el-icon><Lock /></el-icon>模拟支付环境</div>
    </header>

    <main class="payment-main">
      <div class="payment-steps" aria-label="结算进度">
        <div class="done"><span><el-icon><Check /></el-icon></span><b>扫描商品</b></div><i></i>
        <div class="done"><span><el-icon><Check /></el-icon></span><b>确认清单</b></div><i></i>
        <div :class="{ active: paymentStatus === 'pending', done: paymentStatus === 'paid' }">
          <span><el-icon v-if="paymentStatus === 'paid'"><Check /></el-icon><template v-else>3</template></span><b>完成付款</b>
        </div>
      </div>

      <section v-if="!paymentOrder" class="empty-state">
        <el-icon><Warning /></el-icon>
        <h1>没有可支付的订单</h1>
        <p>请返回结算页确认商品后重新创建订单。</p>
        <button type="button" @click="router.push('/checkout')">返回顾客结算端</button>
      </section>

      <section v-else class="payment-layout">
        <aside class="order-panel">
          <div class="panel-heading"><span>订单摘要</span><small>{{ orderNumber }}</small></div>
          <div class="order-items">
            <article v-for="item in paymentOrder.items" :key="item.class_id">
              <div class="item-mark">{{ itemMark(item) }}</div>
              <div><strong>{{ itemName(item) }}</strong><span>数量 x {{ item.count }}</span></div>
              <b>{{ formatMoney(item.subtotal) }}</b>
            </article>
          </div>
          <div class="order-count"><span>商品总数</span><strong>{{ paymentOrder.item_count }} 件</strong></div>
          <div class="order-total"><div><span>应付金额</span><small>金额由服务端商品价格生成</small></div><strong>{{ formatMoney(paymentOrder.amount) }}</strong></div>
          <dl class="order-meta">
            <div><dt>创建时间</dt><dd>{{ formatDate(paymentOrder.created_at) }}</dd></div>
            <div><dt>支付状态</dt><dd :class="`status-${paymentStatus}`">{{ statusText }}</dd></div>
          </dl>
        </aside>

        <section class="pay-panel" aria-live="polite">
          <div v-if="paymentStatus === 'paid'" class="result-state success-state">
            <span class="result-icon"><el-icon><CircleCheckFilled /></el-icon></span>
            <small>PAYMENT COMPLETE</small><h1>付款成功</h1><strong>{{ formatMoney(paymentOrder.amount) }}</strong>
            <p>手机端确认结果已同步至当前收银端。</p>
            <div class="result-reference"><span>订单编号</span><b>{{ orderNumber }}</b></div>
            <button type="button" @click="startNewCheckout">完成并开始新结算</button>
          </div>

          <div v-else-if="paymentStatus === 'expired'" class="result-state expired-state">
            <span class="result-icon"><el-icon><Clock /></el-icon></span>
            <small>QR CODE EXPIRED</small><h1>支付二维码已过期</h1><p>为避免订单串单，请生成新的支付二维码。</p>
            <button type="button" :disabled="regenerating" @click="regenerateOrder">{{ regenerating ? '正在生成' : '重新生成二维码' }}</button>
          </div>

          <template v-else>
            <div class="pay-heading">
              <div><small>模拟扫码支付</small><h1>请使用手机扫描二维码</h1></div>
              <span><i></i>等待付款</span>
            </div>

            <div class="qr-section">
              <div class="qr-frame">
                <img v-if="qrDataUrl" :src="qrDataUrl" width="220" height="220" alt="模拟支付二维码" />
                <el-icon v-else class="qr-loading"><Loading /></el-icon>
              </div>
              <div class="qr-copy">
                <strong>{{ formatMoney(paymentOrder.amount) }}</strong>
                <span>手机与收银设备需连接同一局域网</span>
                <small>二维码有效期 {{ countdownText }}</small>
                <code>{{ paymentUrl }}</code>
              </div>
            </div>

            <div class="waiting-status"><el-icon><Loading /></el-icon><div><strong>正在等待手机端确认</strong><span>页面将自动同步支付结果，无需手动刷新</span></div></div>
            <a class="test-link" :href="localPaymentUrl" target="_blank" rel="noopener">在本机打开测试付款页</a>
            <p class="simulation-note"><el-icon><InfoFilled /></el-icon>本功能仅模拟支付状态，不会调用微信、支付宝或产生真实资金交易。</p>
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
import { ArrowLeft, Check, CircleCheckFilled, Clock, InfoFilled, Loading, Lock, Warning } from '@element-plus/icons-vue'
import { createMockPaymentOrderApi, getMockPaymentOrderApi, getMockPaymentStatusApi } from '@/api/checkout'

const router = useRouter()
const route = useRoute()
const paymentOrder = ref(loadSession('visionpay-payment-order'))
const cartOrder = ref(loadSession('visionpay-checkout-order'))
const qrDataUrl = ref('')
const now = ref(Date.now())
const polling = ref(false)
const regenerating = ref(false)
let statusTimer = null
let countdownTimer = null

const paymentStatus = computed(() => paymentOrder.value?.status || '')
const statusText = computed(() => ({ pending: '等待付款', paid: '付款成功', expired: '已过期' })[paymentStatus.value] || '未知')
const orderNumber = computed(() => paymentOrder.value ? `VP-${paymentOrder.value.order_uuid.slice(0, 8).toUpperCase()}` : '--')
const paymentPath = computed(() => paymentOrder.value ? `/mock-pay/${paymentOrder.value.payment_token}` : '')
const publicOrigin = (import.meta.env.VITE_CHECKOUT_PUBLIC_ORIGIN || window.location.origin).replace(/\/$/, '')
const paymentUrl = computed(() => `${publicOrigin}${paymentPath.value}`)
const localPaymentUrl = computed(() => `${window.location.origin}${paymentPath.value}`)
const remainingSeconds = computed(() => Math.max(0, Math.ceil((new Date(paymentOrder.value?.expires_at || 0).getTime() - now.value) / 1000)))
const countdownText = computed(() => `${String(Math.floor(remainingSeconds.value / 60)).padStart(2, '0')}:${String(remainingSeconds.value % 60).padStart(2, '0')}`)

function loadSession(key) { try { return JSON.parse(sessionStorage.getItem(key)) || null } catch { return null } }
function formatMoney(value) { return `¥ ${Number(value || 0).toFixed(2)}` }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--' }
function itemName(item) { return item.name || item.sku_name || item.class_name || `商品 ${item.class_id}` }
function itemMark(item) { return itemName(item).slice(0, 2).toUpperCase() }

async function renderQrCode() {
  if (!paymentPath.value) return
  qrDataUrl.value = await QRCode.toDataURL(paymentUrl.value, {
    width: 440, margin: 2, errorCorrectionLevel: 'M', color: { dark: '#111827', light: '#ffffff' },
  })
}

async function pollStatus() {
  if (!paymentOrder.value || polling.value || paymentStatus.value !== 'pending') return
  polling.value = true
  try {
    const status = await getMockPaymentStatusApi(paymentOrder.value.order_uuid)
    paymentOrder.value = { ...paymentOrder.value, ...status }
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder.value))
    if (status.status !== 'pending') stopTimers()
  } catch {
    // Keep the current state and retry on the next interval.
  } finally { polling.value = false }
}

function startTimers() {
  stopTimers()
  countdownTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
  statusTimer = window.setInterval(pollStatus, 1000)
}
function stopTimers() {
  window.clearInterval(statusTimer); window.clearInterval(countdownTimer)
  statusTimer = null; countdownTimer = null
}

async function regenerateOrder() {
  if (!cartOrder.value?.items?.length) return router.push('/checkout')
  regenerating.value = true
  try {
    paymentOrder.value = await createMockPaymentOrderApi(cartOrder.value.items)
    sessionStorage.setItem('visionpay-payment-order', JSON.stringify(paymentOrder.value))
    router.replace({ path: '/checkout/payment', query: { token: paymentOrder.value.payment_token } })
    now.value = Date.now()
    await renderQrCode()
    startTimers()
  } finally { regenerating.value = false }
}

function startNewCheckout() {
  sessionStorage.removeItem('visionpay-payment-order'); sessionStorage.removeItem('visionpay-checkout-order')
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
  if (paymentStatus.value === 'pending') {
    await pollStatus()
    if (paymentStatus.value === 'pending') startTimers()
  }
})
onBeforeUnmount(stopTimers)
</script>

<style lang="scss" scoped>
.payment-page { min-height: 100vh; color: #17212b; background: #eef1f4; }
.payment-header { height: 72px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 0 32px; border-bottom: 1px solid #d9e0e6; background: #fff; }
.payment-header > button { min-height: 44px; justify-self: start; display: flex; align-items: center; gap: 7px; border: 0; color: #52616e; background: transparent; cursor: pointer; }.payment-header > button:hover { color: #1d4ed8; }
.brand { display: flex; align-items: center; gap: 10px; }.brand > span { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; background: #1d4ed8; }.brand img { width: 20px; filter: brightness(0) invert(1); }.brand strong { font-size: 16px; }.secure-label { justify-self: end; display: flex; align-items: center; gap: 6px; color: #37664d; font-size: 12px; }
.payment-main { width: min(1120px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 44px; }.payment-steps { width: min(570px, 100%); display: grid; grid-template-columns: auto 1fr auto 1fr auto; align-items: center; margin: 0 auto 26px; }.payment-steps > i { height: 1px; background: #bfc9d2; }.payment-steps > div { display: flex; flex-direction: column; align-items: center; gap: 5px; color: #8b97a2; font-size: 11px; }.payment-steps span { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid #bfc9d2; border-radius: 50%; background: #fff; font-size: 12px; }.payment-steps .done { color: #247754; }.payment-steps .done span { border-color: #27a26f; color: #fff; background: #27a26f; }.payment-steps .active { color: #1d4ed8; }.payment-steps .active span { border: 2px solid #1d4ed8; color: #1d4ed8; font-weight: 800; }
.payment-layout { display: grid; grid-template-columns: minmax(320px, .78fr) minmax(460px, 1.22fr); border: 1px solid #d4dce3; border-radius: 8px; overflow: hidden; background: #fff; box-shadow: 0 18px 46px rgba(28, 43, 57, .08); }.order-panel, .pay-panel { min-width: 0; padding: 28px; }.order-panel { border-right: 1px solid #dce2e7; background: #f8fafb; }.panel-heading, .order-count { display: flex; justify-content: space-between; gap: 12px; }.panel-heading { align-items: baseline; margin-bottom: 16px; }.panel-heading > span { font-size: 18px; font-weight: 800; }.panel-heading small { color: #6f7f8d; font-size: 11px; font-family: ui-monospace, monospace; }
.order-items article { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; align-items: center; gap: 11px; padding: 13px 0; border-bottom: 1px solid #e0e6eb; }.item-mark { width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid #d5dee6; border-radius: 6px; color: #1d4ed8; background: #edf3ff; font-size: 10px; font-weight: 800; }.order-items article > div:nth-child(2) { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.order-items strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }.order-items span { color: #73828f; font-size: 11px; }.order-items b { color: #795512; font-size: 12px; font-variant-numeric: tabular-nums; }.order-count { padding: 14px 0; color: #657482; font-size: 12px; }.order-total { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; padding: 17px 0; border-top: 1px solid #cfd8df; border-bottom: 1px solid #dce3e8; }.order-total > div { display: flex; flex-direction: column; gap: 3px; }.order-total span { font-size: 14px; font-weight: 700; }.order-total small { color: #796121; font-size: 10px; }.order-total > strong { font-size: 28px; font-variant-numeric: tabular-nums; }.order-meta { margin: 14px 0 0; }.order-meta > div { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; color: #71808d; font-size: 11px; }.order-meta dd { margin: 0; color: #354450; }.order-meta .status-pending { color: #9a6813; }.order-meta .status-paid { color: #17734a; }.order-meta .status-expired { color: #a1323e; }
.pay-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.pay-heading > div { display: flex; flex-direction: column; gap: 4px; }.pay-heading small { color: #1d4ed8; font-size: 10px; font-weight: 800; }.pay-heading h1 { margin: 0; font-size: 21px; }.pay-heading > span { display: flex; align-items: center; gap: 7px; padding: 7px 10px; border-radius: 5px; color: #765519; background: #fff7e6; font-size: 11px; }.pay-heading > span i { width: 7px; height: 7px; border-radius: 50%; background: #d49121; box-shadow: 0 0 0 4px #ffedc8; }
.qr-section { min-height: 288px; display: flex; align-items: center; justify-content: center; gap: 28px; margin-top: 20px; border: 1px solid #dce3e8; border-radius: 6px; background: #f8fafb; }.qr-frame { width: 242px; height: 242px; display: grid; place-items: center; padding: 10px; border: 1px solid #cbd5df; border-radius: 6px; background: #fff; }.qr-frame img { display: block; width: 220px; height: 220px; }.qr-loading { font-size: 32px; color: #1d4ed8; animation: spin 1s linear infinite; }.qr-copy { min-width: 0; max-width: 230px; display: flex; flex-direction: column; gap: 9px; }.qr-copy strong { font-size: 30px; font-variant-numeric: tabular-nums; }.qr-copy span { color: #52616e; font-size: 12px; }.qr-copy small { color: #1d4ed8; font-size: 12px; font-variant-numeric: tabular-nums; }.qr-copy code { overflow-wrap: anywhere; color: #71808d; font-size: 10px; line-height: 1.45; }
.waiting-status { display: flex; align-items: center; gap: 11px; margin-top: 14px; padding: 12px 14px; color: #354450; background: #edf4ff; }.waiting-status > .el-icon { flex-shrink: 0; color: #1d4ed8; animation: spin 1s linear infinite; }.waiting-status > div { display: flex; flex-direction: column; gap: 2px; }.waiting-status strong { font-size: 12px; }.waiting-status span { color: #687987; font-size: 10px; }.test-link { min-height: 44px; display: flex; align-items: center; justify-content: center; margin-top: 12px; border: 1px solid #b9c9dd; border-radius: 6px; color: #1d4ed8; text-decoration: none; font-size: 12px; font-weight: 700; }.test-link:hover { border-color: #1d4ed8; background: #f4f7ff; }.simulation-note { display: flex; align-items: flex-start; gap: 7px; margin: 12px 0 0; color: #72561f; font-size: 10px; line-height: 1.5; }
.result-state { min-height: 480px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }.result-icon { width: 76px; height: 76px; display: grid; place-items: center; margin-bottom: 18px; border-radius: 50%; font-size: 48px; }.result-state > small { color: #71808d; font-size: 10px; font-weight: 800; }.result-state h1 { margin: 6px 0; font-size: 28px; }.result-state > strong { margin: 4px 0 8px; font-size: 34px; font-variant-numeric: tabular-nums; }.result-state p { margin: 0 0 22px; color: #657482; font-size: 12px; }.result-state > button, .empty-state button { min-width: 230px; min-height: 48px; border: 0; border-radius: 6px; color: #fff; background: #1d4ed8; cursor: pointer; font-weight: 800; }.result-state > button:disabled { opacity: .55; cursor: wait; }.success-state .result-icon { color: #168658; background: #e1f7ed; }.expired-state .result-icon { color: #b17418; background: #fff1d9; }.result-reference { width: min(330px, 100%); display: flex; justify-content: space-between; gap: 12px; margin-bottom: 22px; padding: 12px; background: #f5f7f9; font-size: 11px; }.result-reference b { font-family: ui-monospace, monospace; }
.empty-state { min-height: 430px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid #d4dce3; border-radius: 8px; background: #fff; text-align: center; }.empty-state > .el-icon { font-size: 48px; color: #b17418; }.empty-state h1 { margin: 15px 0 6px; }.empty-state p { margin: 0 0 20px; color: #657482; }
@keyframes spin { to { transform: rotate(360deg); } } @media (prefers-reduced-motion: reduce) { .qr-loading, .waiting-status > .el-icon { animation: none; } }
@media (max-width: 900px) { .payment-header { grid-template-columns: 1fr auto; padding: 0 18px; }.payment-header .brand { display: none; }.payment-layout { grid-template-columns: 1fr; }.order-panel { border-right: 0; border-bottom: 1px solid #dce2e7; }.payment-main { width: min(100% - 24px, 680px); }.qr-section { padding: 24px; } }
@media (max-width: 560px) { .payment-header > button span, .secure-label { display: none; }.payment-main { width: calc(100% - 20px); padding-top: 18px; }.payment-steps b { display: none; }.order-panel, .pay-panel { padding: 20px 16px; }.qr-section { flex-direction: column; gap: 16px; text-align: center; }.qr-copy { align-items: center; }.pay-heading { align-items: center; }.pay-heading h1 { font-size: 18px; }.pay-heading > span { flex-shrink: 0; }.qr-frame { width: 232px; height: 232px; }.qr-frame img { width: 210px; height: 210px; } }
</style>
