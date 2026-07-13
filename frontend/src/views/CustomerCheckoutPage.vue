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
          <button type="button" :class="{ active: sourceMode === 'camera' }" @click="sourceMode = 'camera'"><el-icon><Camera /></el-icon>实时摄像头</button>
          <button type="button" :class="{ active: sourceMode === 'upload' }" @click="sourceMode = 'upload'"><el-icon><UploadFilled /></el-icon>上传图片</button>
        </div>

        <div v-if="sourceMode === 'camera'" class="camera-stage">
          <div class="camera-toolbar"><span><i></i>实时画面</span><small>CAM-01 · 1080P</small></div>
          <div class="camera-view">
            <div class="scan-frame"><span></span><span></span><span></span><span></span><b></b></div>
            <div class="camera-placeholder"><el-icon><Camera /></el-icon><strong>摄像头画面区域</strong><span>将商品平铺放置在识别区域内</span></div>
          </div>
          <div class="capture-tip"><el-icon><CircleCheckFilled /></el-icon><span>系统将自动识别进入画面的商品</span></div>
        </div>

        <div v-else class="upload-stage" @dragover.prevent @drop.prevent="handleDrop">
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
          <div><span>识别状态</span><strong>已完成</strong></div>
          <div><span>画面内商品</span><strong>{{ totalItems }} 件</strong></div>
          <div><span>平均置信度</span><strong>94.2%</strong></div>
        </div>
      </section>

      <section class="basket-section">
        <div class="basket-heading">
          <div><span>步骤 2</span><h2>确认商品清单</h2></div>
          <strong>{{ totalItems }} 件</strong>
        </div>

        <div class="price-notice"><el-icon><InfoFilled /></el-icon><span>商品价目表尚未接入，当前仅展示识别与数量框架。</span></div>

        <div class="product-list">
          <article v-for="item in products" :key="item.id" class="product-item">
            <div class="product-thumb"><span>{{ item.short }}</span></div>
            <div class="product-copy">
              <strong>{{ item.name }}</strong>
              <span>{{ item.category }} · 置信度 {{ item.confidence }}</span>
              <b>价格待接入</b>
            </div>
            <div class="quantity-control">
              <button type="button" :disabled="item.quantity <= 1" @click="item.quantity--"><el-icon><Minus /></el-icon></button>
              <span>{{ item.quantity }}</span>
              <button type="button" @click="item.quantity++"><el-icon><Plus /></el-icon></button>
            </div>
            <button type="button" class="remove-button" aria-label="移除商品" @click="removeProduct(item.id)"><el-icon><Delete /></el-icon></button>
          </article>

          <div v-if="!products.length" class="empty-basket"><el-icon><ShoppingCart /></el-icon><strong>暂未识别到商品</strong><span>请重新扫描或上传商品图片</span></div>
        </div>

        <footer class="settlement-panel">
          <div class="settlement-summary"><span>应付金额</span><strong>¥ --</strong><small>等待价目表服务接入</small></div>
          <button type="button" :disabled="!products.length" @click="goToPayment"><span>确认商品并去结算</span><el-icon><ArrowRight /></el-icon></button>
          <p>继续即表示您已确认以上商品和数量</p>
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Camera, CircleCheckFilled, Delete, InfoFilled, Minus, Plus, Refresh, ShoppingCart, UploadFilled } from '@element-plus/icons-vue'

const router = useRouter()
const sourceMode = ref('camera')
const uploadInputRef = ref(null)
const previewUrl = ref('')
const seedProducts = () => [
  { id: 1, name: '可口可乐 330ml', category: '饮料', confidence: '97.6%', short: '可乐', quantity: 1 },
  { id: 2, name: '原味薯片', category: '休闲食品', confidence: '94.1%', short: '薯片', quantity: 1 },
  { id: 3, name: '纯牛奶 250ml', category: '乳制品', confidence: '90.9%', short: '牛奶', quantity: 1 },
]
const products = ref(seedProducts())
const totalItems = computed(() => products.value.reduce((sum, item) => sum + item.quantity, 0))

function setPreview(file) {
  if (!file?.type?.startsWith('image/')) return
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
}
function handleUpload(event) { setPreview(event.target.files?.[0]); event.target.value = '' }
function handleDrop(event) { setPreview(event.dataTransfer.files?.[0]) }
function removeProduct(id) { products.value = products.value.filter((item) => item.id !== id) }
function resetDemo() { products.value = seedProducts(); sourceMode.value = 'camera'; if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function goToPayment() { router.push({ path: '/checkout/payment', query: { items: totalItems.value } }) }
onBeforeUnmount(() => { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value) })
</script>

<style lang="scss" scoped>
.checkout-page { min-height: 100vh; color: #17212b; background: #eef1f4; }
.checkout-header { height: 74px; display: flex; align-items: center; justify-content: space-between; padding: 0 34px; border-bottom: 1px solid #d9e0e6; background: #fff; }.brand { display: flex; align-items: center; gap: 12px; }.brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 7px; background: #1d4ed8; }.brand-mark img { width: 22px; filter: brightness(0) invert(1); }.brand > div { display: flex; flex-direction: column; }.brand strong { font-size: 18px; }.brand span { color: #70808f; font-size: 11px; }.header-status { display: grid; grid-template-columns: 8px auto auto; align-items: center; gap: 7px; color: #3a4a58; font-size: 12px; }.header-status i { width: 8px; height: 8px; border-radius: 50%; background: #16a36d; box-shadow: 0 0 0 4px #e0f5ec; }.header-status small { margin-left: 6px; padding-left: 12px; border-left: 1px solid #dce2e7; color: #82909d; }
.checkout-main { min-height: calc(100vh - 74px); display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(390px, .65fr); }.capture-section { min-width: 0; padding: 28px 30px 32px; border-right: 1px solid #d8dfe5; }.section-heading, .basket-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }.section-heading > div, .basket-heading > div { display: flex; flex-direction: column; gap: 4px; }.section-heading span, .basket-heading span { color: #1d4ed8; font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }.section-heading h1, .basket-heading h2 { margin: 0; font-size: 23px; letter-spacing: -.02em; }.reset-button { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid #cfd8df; border-radius: 5px; color: #526170; background: #fff; cursor: pointer; font-size: 12px; }.reset-button:hover { border-color: #1d4ed8; color: #1d4ed8; }
.source-tabs { display: inline-grid; grid-template-columns: 1fr 1fr; margin-bottom: 12px; border: 1px solid #cfd8df; border-radius: 6px; overflow: hidden; }.source-tabs button { display: flex; align-items: center; justify-content: center; gap: 7px; min-width: 150px; height: 40px; border: 0; border-right: 1px solid #cfd8df; color: #657482; background: #fff; cursor: pointer; }.source-tabs button:last-child { border-right: 0; }.source-tabs button.active { color: #fff; background: #1d4ed8; }
.camera-stage, .upload-stage { border: 1px solid #cbd4dc; background: #fff; }.camera-toolbar { height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid #2f3d49; color: #dfe7ec; background: #1e2a34; font-size: 11px; }.camera-toolbar span { display: flex; align-items: center; gap: 7px; }.camera-toolbar i { width: 7px; height: 7px; border-radius: 50%; background: #2bd88f; }.camera-toolbar small { color: #8fa0ad; }.camera-view { position: relative; aspect-ratio: 16 / 9; min-height: 340px; display: grid; place-items: center; overflow: hidden; background: #17212a; }.camera-placeholder { display: flex; flex-direction: column; align-items: center; gap: 7px; color: #aebbc5; }.camera-placeholder .el-icon { font-size: 42px; color: #657682; }.camera-placeholder strong { color: #d8e1e7; font-size: 14px; }.camera-placeholder span { font-size: 11px; }.scan-frame { position: absolute; inset: 13%; z-index: 2; }.scan-frame > span { position: absolute; width: 38px; height: 38px; border-color: #48d79f; border-style: solid; }.scan-frame > span:nth-child(1) { top: 0; left: 0; border-width: 3px 0 0 3px; }.scan-frame > span:nth-child(2) { top: 0; right: 0; border-width: 3px 3px 0 0; }.scan-frame > span:nth-child(3) { bottom: 0; left: 0; border-width: 0 0 3px 3px; }.scan-frame > span:nth-child(4) { right: 0; bottom: 0; border-width: 0 3px 3px 0; }.scan-frame b { position: absolute; top: 48%; left: 4%; right: 4%; height: 1px; background: #48d79f; opacity: .7; }.capture-tip { height: 45px; display: flex; align-items: center; gap: 8px; padding: 0 14px; color: #476050; background: #effaf5; font-size: 12px; }.capture-tip .el-icon { color: #16a36d; }
.upload-stage { min-height: 440px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; border-style: dashed; color: #6f7f8d; }.upload-stage > .el-icon { font-size: 40px; color: #1d4ed8; }.upload-stage strong { color: #273643; font-size: 15px; }.upload-stage span { font-size: 11px; }.upload-stage button { margin-top: 8px; padding: 9px 18px; border: 0; border-radius: 5px; color: #fff; background: #1d4ed8; cursor: pointer; }.upload-stage img { max-width: 90%; max-height: 350px; object-fit: contain; }
.capture-footer { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 14px; border: 1px solid #d4dce3; background: #fff; }.capture-footer div { display: flex; flex-direction: column; gap: 4px; padding: 13px 15px; border-right: 1px solid #dfe5ea; }.capture-footer div:last-child { border-right: 0; }.capture-footer span { color: #7b8996; font-size: 10px; }.capture-footer strong { font-size: 14px; }
.basket-section { min-width: 0; display: flex; flex-direction: column; padding: 28px 28px 24px; background: #fff; }.basket-heading { margin-bottom: 14px; }.basket-heading > strong { min-width: 42px; padding: 6px 8px; border-radius: 999px; color: #1d4ed8; background: #eaf0ff; text-align: center; font-size: 12px; }.price-notice { display: flex; align-items: flex-start; gap: 8px; padding: 10px 11px; border-left: 3px solid #e49a24; color: #79591d; background: #fff8e9; font-size: 11px; line-height: 1.55; }.price-notice .el-icon { margin-top: 2px; flex-shrink: 0; }.product-list { min-height: 0; flex: 1; overflow-y: auto; margin: 15px -5px 15px 0; padding-right: 5px; }.product-item { position: relative; display: grid; grid-template-columns: 54px minmax(0, 1fr) auto 27px; align-items: center; gap: 11px; padding: 13px 0; border-bottom: 1px solid #e5e9ed; }.product-thumb { width: 54px; height: 54px; display: grid; place-items: center; border: 1px solid #dce3e8; border-radius: 6px; color: #1d4ed8; background: #f2f6ff; font-size: 10px; font-weight: 800; }.product-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }.product-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }.product-copy span { color: #82909d; font-size: 10px; }.product-copy b { color: #b07818; font-size: 11px; }.quantity-control { display: grid; grid-template-columns: 26px 30px 26px; align-items: center; border: 1px solid #d5dde4; border-radius: 5px; overflow: hidden; }.quantity-control button { height: 28px; border: 0; color: #52616e; background: #f6f8fa; cursor: pointer; }.quantity-control button:disabled { color: #bdc5cb; cursor: not-allowed; }.quantity-control span { text-align: center; font-size: 12px; font-weight: 800; }.remove-button { width: 27px; height: 27px; border: 0; color: #97a2ab; background: transparent; cursor: pointer; }.remove-button:hover { color: #d44c5c; }.empty-basket { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #84919c; }.empty-basket .el-icon { font-size: 38px; }.empty-basket strong { color: #53616d; }.empty-basket span { font-size: 11px; }
.settlement-panel { padding-top: 18px; border-top: 1px solid #dce2e7; }.settlement-summary { display: grid; grid-template-columns: 1fr auto; align-items: end; margin-bottom: 14px; }.settlement-summary span { color: #52616e; font-size: 13px; }.settlement-summary strong { grid-row: span 2; color: #152331; font-size: 28px; }.settlement-summary small { color: #9a6a16; font-size: 10px; }.settlement-panel > button { width: 100%; height: 50px; display: flex; align-items: center; justify-content: center; gap: 10px; border: 0; border-radius: 6px; color: #fff; background: #1d4ed8; cursor: pointer; font-size: 15px; font-weight: 800; }.settlement-panel > button:hover { background: #173fae; }.settlement-panel > button:disabled { background: #aeb9c5; cursor: not-allowed; }.settlement-panel p { margin: 9px 0 0; color: #919ca6; text-align: center; font-size: 10px; }
@media (max-width: 1050px) { .checkout-main { grid-template-columns: 1fr; }.capture-section { border-right: 0; border-bottom: 1px solid #d8dfe5; }.basket-section { min-height: 620px; }.camera-view { min-height: 0; } }
@media (max-width: 640px) { .checkout-header { height: 66px; padding: 0 16px; }.header-status small { display: none; }.checkout-main { min-height: calc(100vh - 66px); }.capture-section, .basket-section { padding: 20px 16px; }.section-heading h1, .basket-heading h2 { font-size: 20px; }.source-tabs { width: 100%; }.source-tabs button { min-width: 0; }.capture-footer { grid-template-columns: 1fr; }.capture-footer div { border-right: 0; border-bottom: 1px solid #dfe5ea; }.capture-footer div:last-child { border-bottom: 0; }.product-item { grid-template-columns: 48px minmax(0, 1fr) 27px; }.product-thumb { width: 48px; height: 48px; }.quantity-control { grid-column: 2 / 3; justify-self: start; }.remove-button { grid-column: 3; grid-row: 1; } }
</style>
