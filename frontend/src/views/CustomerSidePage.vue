<template>
  <div class="customer-side-page">
    <section class="launch-card">
      <div class="launch-icon"><el-icon><Connection /></el-icon></div>
      <span class="eyebrow">CUSTOMER CHECKOUT</span>
      <h1>用户侧自助结算</h1>
      <p>用户侧运行在独立的 5174 端口，用于测试商品识别、购物篮计价和付款确认流程。</p>

      <div class="target-address">
        <span>目标地址</span>
        <code>{{ checkoutUrl }}</code>
      </div>

      <button type="button" class="launch-button" @click="openCustomerSide">
        <span>在新窗口打开用户侧</span>
        <el-icon><TopRight /></el-icon>
      </button>

      <div class="launch-tip">
        <el-icon><InfoFilled /></el-icon>
        <span>跳转前请先在 frontend 目录执行 <code>npm run dev:checkout</code>。</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { Connection, InfoFilled, TopRight } from '@element-plus/icons-vue'

const checkoutUrl = import.meta.env.VITE_CHECKOUT_URL || 'http://localhost:5174/checkout'

function openCustomerSide() {
  window.open(checkoutUrl, '_blank', 'noopener,noreferrer')
}
</script>

<style lang="scss" scoped>
.customer-side-page {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 36px;
  background:
    radial-gradient(circle at 20% 15%, rgba(79, 70, 229, 0.09), transparent 34%),
    radial-gradient(circle at 85% 80%, rgba(16, 185, 129, 0.08), transparent 30%),
    $bg-color;
}

.launch-card {
  width: min(560px, 100%);
  padding: 42px;
  border: 1px solid $border-color;
  border-radius: 18px;
  background: $surface-color;
  box-shadow: 0 22px 55px rgba(15, 23, 42, 0.09);
  text-align: center;
}

.launch-icon {
  width: 66px;
  height: 66px;
  display: grid;
  place-items: center;
  margin: 0 auto 18px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #4f46e5, #2563eb);
  box-shadow: 0 12px 25px rgba(79, 70, 229, 0.25);
  font-size: 30px;
}

.eyebrow {
  color: $primary-color;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

h1 {
  margin: 9px 0 10px;
  color: $text-primary;
  font-size: 28px;
}

p {
  max-width: 430px;
  margin: 0 auto;
  color: $text-secondary;
  font-size: 14px;
  line-height: 1.75;
}

.target-address {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 28px 0 18px;
  padding: 14px 16px;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: $surface-muted;
  text-align: left;
}

.target-address span {
  color: $text-secondary;
  font-size: 10px;
  font-weight: 700;
}

.target-address code {
  overflow: hidden;
  color: $text-primary;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.launch-button {
  width: 100%;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: $border-radius-md;
  color: #fff;
  background: $primary-color;
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.2);
  cursor: pointer;
  font-size: 14px;
  font-weight: 800;
  transition: transform 0.2s, box-shadow 0.2s, background 0.2s;
}

.launch-button:hover {
  background: #4338ca;
  box-shadow: 0 13px 25px rgba(79, 70, 229, 0.26);
  transform: translateY(-1px);
}

.launch-tip {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 7px;
  margin-top: 16px;
  color: $text-placeholder;
  font-size: 11px;
  line-height: 1.6;
}

.launch-tip .el-icon {
  margin-top: 3px;
  flex-shrink: 0;
}

.launch-tip code {
  color: $text-secondary;
}

@media (max-width: 640px) {
  .customer-side-page { padding: 18px; }
  .launch-card { padding: 30px 22px; }
  h1 { font-size: 24px; }
}
</style>
