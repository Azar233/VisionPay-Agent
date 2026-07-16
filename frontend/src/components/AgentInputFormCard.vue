<template>
  <section v-if="form.form_type === 'dataset_add_samples'" class="agent-input-form">
    <div class="form-heading">
      <div class="form-mark"><el-icon><EditPen /></el-icon></div>
      <div><span>需要补充的信息</span><strong>{{ form.title || '补充样品信息' }}</strong></div>
    </div>
    <p>{{ form.description }}</p>

    <div class="form-grid">
      <label>
        <span>草稿数据集 ID <b>必填</b></span>
        <el-input-number v-model="values.dataset_id" :min="1" :controls="false" placeholder="例如 6" />
      </label>
      <label>
        <span>添加模式 <b>必填</b></span>
        <el-select v-model="values.mode">
          <el-option label="新建商品训练图" value="train_new" />
          <el-option label="已有商品训练图" value="train_existing" />
          <el-option label="val/test 结账场景" value="scene" />
        </el-select>
      </label>
    </div>

    <div v-if="values.mode === 'train_new'" class="form-grid product-fields">
      <label><span>商品名称 <b>必填</b></span><el-input v-model.trim="values.name" placeholder="例如：可口可乐零度 500ml" /></label>
      <label><span>类别英文名 <b>必填</b></span><el-input v-model.trim="values.class_name" placeholder="例如：coca_cola_zero" /></label>
      <label><span>价格（元）<b>必填</b></span><el-input-number v-model="values.unit_price" :min="0" :precision="2" :step="0.5" :controls="false" placeholder="例如：3.50" /></label>
      <label><span>条码 <em>可选</em></span><el-input v-model.trim="values.barcode" placeholder="可留空" /></label>
    </div>

    <div v-else-if="values.mode === 'train_existing'" class="form-grid">
      <label><span>已有商品 ID <b>必填</b></span><el-input-number v-model="values.existing_product_id" :min="1" :controls="false" placeholder="例如：12" /></label>
    </div>

    <div v-else class="scene-note">结账场景不需要填写商品字段；提交后请在数据集页面选择图片并逐图绘制检测框。</div>

    <div class="form-actions">
      <span>提交后，Agent 将创建人工选图与标注交接。</span>
      <el-button type="primary" :disabled="submitted" @click="submit">{{ submitted ? '已提交' : '继续创建交接' }}</el-button>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'

const props = defineProps({ form: { type: Object, required: true } })
const emit = defineEmits(['submit'])
const submitted = ref(false)
const values = reactive({
  dataset_id: undefined,
  mode: 'train_new',
  name: '',
  class_name: '',
  unit_price: undefined,
  barcode: '',
  existing_product_id: undefined,
})

function hydrate(form) {
  const defaults = form?.defaults || {}
  values.dataset_id = defaults.dataset_id || undefined
  values.mode = defaults.mode || 'train_new'
  submitted.value = false
}

watch(() => props.form, hydrate, { immediate: true })

function submit() {
  if (!values.dataset_id) return ElMessage.warning('请填写草稿数据集 ID')
  if (values.mode === 'train_new' && (!values.name || !values.class_name || values.unit_price === undefined || values.unit_price === null)) {
    return ElMessage.warning('请填写商品名称、类别英文名和价格')
  }
  if (values.mode === 'train_existing' && !values.existing_product_id) return ElMessage.warning('请填写已有商品 ID')
  submitted.value = true
  emit('submit', { ...values })
}
</script>

<style lang="scss" scoped>
.agent-input-form { margin-top: 16px; padding: 16px; border: 1px solid rgba(124,58,237,.28); border-radius: 18px; background: linear-gradient(145deg, rgba(250,247,255,.96), rgba(255,255,255,.98)); box-shadow: 0 12px 30px rgba(76,29,149,.08); }.form-heading { display: flex; align-items: center; gap: 10px; }.form-mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 11px; color: #fff; background: linear-gradient(145deg,#8b5cf6,#6d28d9); }.form-heading div:last-child { display: flex; flex-direction: column; gap: 2px; }.form-heading span { color: #7c3aed; font-size: 10px; font-weight: 800; letter-spacing: .06em; }.form-heading strong { color: $text-primary; font-size: 14px; }.agent-input-form > p { margin: 12px 0; color: $text-secondary; font-size: 12px; line-height: 1.6; }.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 10px; }.product-fields { margin-top: 10px; }.form-grid label { display: flex; flex-direction: column; gap: 6px; }.form-grid label > span { color: $text-secondary; font-size: 11px; font-weight: 700; }.form-grid b { margin-left: 4px; color: #dc2626; font-size: 9px; }.form-grid em { margin-left: 4px; color: $text-placeholder; font-size: 9px; font-style: normal; font-weight: 500; }.form-grid :deep(.el-input-number),.form-grid :deep(.el-select) { width: 100%; }.scene-note { margin-top: 10px; padding: 10px; border-radius: 10px; color: $text-secondary; background: rgba(124,58,237,.06); font-size: 11px; line-height: 1.6; }.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; }.form-actions > span { color: $text-placeholder; font-size: 10px; line-height: 1.5; }.form-actions .el-button { flex: 0 0 auto; }.form-actions .el-button:not(.is-disabled) { background: #7c3aed; border-color: #7c3aed; }
@media (max-width: 640px) { .form-grid { grid-template-columns: 1fr; }.form-actions { align-items: flex-start; flex-direction: column; }.form-actions .el-button { width: 100%; } }
:global(html.dark .agent-input-form) { border-color: rgba(191,90,242,.3); background: linear-gradient(145deg,rgba(65,40,100,.4),rgba(44,44,46,.96)); box-shadow: 0 14px 34px rgba(0,0,0,.28); }:global(html.dark .agent-input-form .form-heading strong) { color: #f5f5f7; }:global(html.dark .agent-input-form .scene-note) { background: rgba(191,90,242,.12); }
</style>
