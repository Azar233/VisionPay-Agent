<template>
  <div class="payment-page">
    <header class="payment-header">
      <button type="button" @click="router.push('/checkout')"><el-icon><ArrowLeft /></el-icon><span>返回商品确认</span></button>
      <div class="brand"><span><img src="/favicon.svg" alt="VisionPay" /></span><strong>VisionPay 自助结算</strong></div>
      <div class="secure-label"><el-icon><Lock /></el-icon>安全支付环境</div>
    </header>

    <main class="payment-main">
      <div class="payment-steps">
        <div class="done"><span><el-icon><Check /></el-icon></span><b>扫描商品</b></div>
        <i></i>
        <div class="done"><span><el-icon><Check /></el-icon></span><b>确认清单</b></div>
        <i></i>
        <div class="active"><span>3</span><b>完成付款</b></div>
      </div>

      <section class="payment-layout">
        <aside class="order-panel">
          <div class="panel-heading"><span>订单摘要</span><small>演示订单</small></div>
          <div class="order-number"><span>订单编号</span><strong>VP-DEMO-2026</strong></div>
          <div class="order-items">
            <article v-for="item in orderItems" :key="item.name">
              <div class="item-mark">{{ item.short }}</div>
              <div><strong>{{ item.name }}</strong><span>数量 × {{ item.quantity }}</span></div>
              <b>待定价</b>
            </article>
          </div>
          <div class="order-count"><span>商品总数</span><strong>{{ itemCount }} 件</strong></div>
          <div class="order-total"><div><span>应付金额</span><small>价目表服务尚未接入</small></div><strong>¥ --</strong></div>
        </aside>

        <section class="pay-panel">
          <div class="panel-heading"><span>选择付款方式</span><small>请选择一种方式</small></div>
          <div class="method-list">
            <button v-for="method in methods" :key="method.id" type="button" :class="{ active: selectedMethod === method.id }" @click="selectedMethod = method.id">
              <span :class="['method-icon', method.id]"><el-icon><component :is="method.icon" /></el-icon></span>
              <div><strong>{{ method.name }}</strong><small>{{ method.description }}</small></div>
              <i><el-icon v-if="selectedMethod === method.id"><Check /></el-icon></i>
            </button>
          </div>

          <div v-if="selectedMethod !== 'card'" class="qr-section">
            <div class="qr-placeholder" aria-label="支付二维码占位">
              <span v-for="(filled, index) in qrCells" :key="index" :class="{ filled }"></span>
            </div>
            <div class="qr-copy"><strong>支付二维码占位</strong><span>接入支付服务后，将在此处生成动态二维码</span><small>二维码有效时间 --:--</small></div>
          </div>
          <div v-else class="card-section"><el-icon><CreditCard /></el-icon><strong>银行卡终端占位</strong><span>接入 POS 设备后，将在此处显示刷卡状态。</span></div>

          <div class="integration-notice"><el-icon><InfoFilled /></el-icon><div><strong>当前为前端框架预览</strong><span>金额计算、订单创建和真实支付能力均未连接。</span></div></div>
          <button class="pay-button" type="button" disabled>等待价格与支付服务接入</button>
        </section>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Check, CreditCard, InfoFilled, Iphone, Lock, Wallet } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const selectedMethod = ref('wechat')
const methods = [
  { id: 'wechat', name: '微信支付', description: '使用微信扫描二维码', icon: Iphone },
  { id: 'alipay', name: '支付宝', description: '使用支付宝扫描二维码', icon: Wallet },
  { id: 'card', name: '银行卡', description: '使用收银台刷卡终端', icon: CreditCard },
]
const orderItems = [
  { name: '可口可乐 330ml', short: '可乐', quantity: 1 },
  { name: '原味薯片', short: '薯片', quantity: 1 },
  { name: '纯牛奶 250ml', short: '牛奶', quantity: 1 },
]
const itemCount = computed(() => Number(route.query.items) || orderItems.reduce((sum, item) => sum + item.quantity, 0))
const qrCells = Array.from({ length: 169 }, (_, index) => {
  const row = Math.floor(index / 13)
  const col = index % 13
  const corner = (row < 4 && col < 4) || (row < 4 && col > 8) || (row > 8 && col < 4)
  return corner || ((row * 7 + col * 3 + index) % 5 < 2)
})
</script>

<style lang="scss" scoped>
.payment-page { min-height: 100vh; color: #17212b; background: #eef1f4; }.payment-header { height: 72px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 0 32px; border-bottom: 1px solid #d9e0e6; background: #fff; }.payment-header > button { justify-self: start; display: flex; align-items: center; gap: 7px; border: 0; color: #52616e; background: transparent; cursor: pointer; }.payment-header > button:hover { color: #1d4ed8; }.brand { display: flex; align-items: center; gap: 10px; }.brand > span { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; background: #1d4ed8; }.brand img { width: 20px; filter: brightness(0) invert(1); }.brand strong { font-size: 16px; }.secure-label { justify-self: end; display: flex; align-items: center; gap: 6px; color: #4a6757; font-size: 11px; }
.payment-main { width: min(1120px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 44px; }.payment-steps { width: min(570px, 100%); display: grid; grid-template-columns: auto 1fr auto 1fr auto; align-items: center; margin: 0 auto 26px; }.payment-steps > i { height: 1px; background: #bfc9d2; }.payment-steps > div { display: flex; flex-direction: column; align-items: center; gap: 5px; color: #8b97a2; font-size: 10px; }.payment-steps span { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid #bfc9d2; border-radius: 50%; background: #fff; font-size: 12px; }.payment-steps .done { color: #247754; }.payment-steps .done span { border-color: #27a26f; color: #fff; background: #27a26f; }.payment-steps .active { color: #1d4ed8; }.payment-steps .active span { border: 2px solid #1d4ed8; color: #1d4ed8; font-weight: 800; }
.payment-layout { display: grid; grid-template-columns: minmax(320px, .75fr) minmax(440px, 1.25fr); border: 1px solid #d4dce3; background: #fff; box-shadow: 0 18px 46px rgba(28, 43, 57, .08); }.order-panel, .pay-panel { min-width: 0; padding: 25px; }.order-panel { border-right: 1px solid #dce2e7; background: #f8fafb; }.panel-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }.panel-heading > span { font-size: 18px; font-weight: 800; }.panel-heading small { color: #82909c; font-size: 10px; }.order-number, .order-count { display: flex; justify-content: space-between; gap: 12px; padding: 11px 0; border-top: 1px solid #dde4e9; color: #71808d; font-size: 11px; }.order-number strong, .order-count strong { color: #354450; font-size: 11px; }.order-items { margin: 5px 0 10px; }.order-items article { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 1px solid #e0e6eb; }.item-mark { width: 42px; height: 42px; display: grid; place-items: center; border: 1px solid #d5dee6; border-radius: 5px; color: #1d4ed8; background: #edf3ff; font-size: 9px; font-weight: 800; }.order-items article > div:nth-child(2) { min-width: 0; display: flex; flex-direction: column; gap: 3px; }.order-items strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }.order-items span { color: #84919c; font-size: 10px; }.order-items b { color: #a4741c; font-size: 10px; }.order-total { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; padding-top: 17px; border-top: 1px solid #cfd8df; }.order-total > div { display: flex; flex-direction: column; gap: 3px; }.order-total span { font-size: 13px; font-weight: 700; }.order-total small { color: #a4741c; font-size: 9px; }.order-total > strong { font-size: 27px; }
.method-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }.method-list > button { position: relative; min-width: 0; display: grid; grid-template-columns: 34px minmax(0, 1fr) 18px; align-items: center; gap: 9px; padding: 11px; border: 1px solid #d8e0e6; border-radius: 6px; color: #354450; background: #fff; text-align: left; cursor: pointer; }.method-list > button:hover { border-color: #8aa8dd; }.method-list > button.active { border: 2px solid #1d4ed8; padding: 10px; background: #f5f8ff; }.method-icon { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 5px; color: #fff; background: #28794f; }.method-icon.alipay { background: #1677ff; }.method-icon.card { background: #596a7a; }.method-list button > div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }.method-list strong { white-space: nowrap; font-size: 11px; }.method-list small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #84919c; font-size: 9px; }.method-list button > i { width: 18px; height: 18px; display: grid; place-items: center; border: 1px solid #b9c4ce; border-radius: 50%; color: #fff; }.method-list button.active > i { border-color: #1d4ed8; background: #1d4ed8; }
.qr-section { min-height: 260px; display: flex; align-items: center; justify-content: center; gap: 25px; margin-top: 18px; border: 1px solid #dce3e8; background: #f8fafb; }.qr-placeholder { width: 156px; height: 156px; display: grid; grid-template-columns: repeat(13, 1fr); grid-template-rows: repeat(13, 1fr); gap: 1px; padding: 10px; border: 1px solid #cad4dc; background: #fff; }.qr-placeholder span { background: #fff; }.qr-placeholder span.filled { background: #17212b; }.qr-copy { max-width: 190px; display: flex; flex-direction: column; gap: 8px; }.qr-copy strong { font-size: 14px; }.qr-copy span { color: #71808d; font-size: 11px; line-height: 1.6; }.qr-copy small { color: #1d4ed8; font-size: 10px; }.card-section { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; margin-top: 18px; border: 1px solid #dce3e8; color: #71808d; background: #f8fafb; }.card-section .el-icon { font-size: 44px; color: #596a7a; }.card-section strong { color: #354450; }.card-section span { font-size: 11px; }
.integration-notice { display: flex; align-items: flex-start; gap: 9px; margin-top: 14px; padding: 10px 12px; border-left: 3px solid #d99222; color: #72561f; background: #fff8e8; }.integration-notice > div { display: flex; flex-direction: column; gap: 3px; }.integration-notice strong { font-size: 11px; }.integration-notice span { font-size: 10px; }.pay-button { width: 100%; height: 48px; margin-top: 14px; border: 0; border-radius: 6px; color: #fff; background: #aab6c1; cursor: not-allowed; font-weight: 800; }
@media (max-width: 860px) { .payment-header { grid-template-columns: 1fr auto; padding: 0 18px; }.payment-header .brand { display: none; }.payment-layout { grid-template-columns: 1fr; }.order-panel { border-right: 0; border-bottom: 1px solid #dce2e7; }.method-list { grid-template-columns: 1fr; }.method-list > button { grid-template-columns: 34px minmax(0, 1fr) 18px; }.payment-main { width: min(100% - 24px, 680px); }.qr-section { padding: 20px; } }
@media (max-width: 520px) { .payment-header > button span, .secure-label { display: none; }.payment-main { width: calc(100% - 20px); padding-top: 18px; }.payment-steps b { display: none; }.order-panel, .pay-panel { padding: 18px 15px; }.qr-section { flex-direction: column; text-align: center; }.qr-copy { align-items: center; }.panel-heading > span { font-size: 16px; } }
</style>
