<template>
  <section class="agent-input-form">
    <div class="form-heading">
      <div class="form-mark"><el-icon><EditPen /></el-icon></div>
      <div><span>需要补充的信息</span><strong>{{ normalizedForm.title }}</strong></div>
    </div>
    <p v-if="normalizedForm.description">{{ normalizedForm.description }}</p>

    <div class="form-grid">
      <label
        v-for="field in visibleFields"
        :key="field.name"
        :class="{ wide: ['textarea', 'boolean'].includes(field.type) }"
      >
        <span>{{ field.label }} <b v-if="field.required">必填</b><em v-else>可选</em></span>

        <el-input
          v-if="field.type === 'text'"
          v-model="values[field.name]"
          :placeholder="field.placeholder"
          clearable
        />
        <el-input
          v-else-if="field.type === 'textarea'"
          v-model="values[field.name]"
          type="textarea"
          :rows="3"
          :placeholder="field.placeholder"
          resize="vertical"
        />
        <el-input-number
          v-else-if="field.type === 'integer' || field.type === 'number'"
          v-model="values[field.name]"
          v-bind="numberInputProps(field)"
          :placeholder="field.placeholder"
        />
        <el-select
          v-else-if="field.type === 'select' || field.type === 'multiselect'"
          v-model="values[field.name]"
          :multiple="field.type === 'multiselect'"
          :placeholder="field.placeholder || '请选择'"
          clearable
        >
          <el-option v-for="option in field.options" :key="String(option.value)" :label="option.label" :value="option.value" />
        </el-select>
        <el-switch
          v-else-if="field.type === 'boolean'"
          v-model="values[field.name]"
          inline-prompt
          active-text="是"
          inactive-text="否"
        />
        <el-date-picker
          v-else-if="field.type === 'date'"
          v-model="values[field.name]"
          type="date"
          value-format="YYYY-MM-DD"
          :placeholder="field.placeholder || '选择日期'"
        />
        <small v-if="field.help_text">{{ field.help_text }}</small>
      </label>
    </div>

    <div class="form-actions">
      <span>提交后将返回 {{ agentLabel }} 继续处理；写操作仍需影响预览与确认。</span>
      <el-button type="primary" :disabled="submitted" @click="submit">
        {{ submitted ? '已提交' : normalizedForm.submit_label || '提交并继续' }}
      </el-button>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'

const props = defineProps({ form: { type: Object, required: true } })
const emit = defineEmits(['submit'])
const submitted = ref(false)
const values = reactive({})

const agentNames = {
  detection: 'Detection Agent',
  dataset: 'Dataset Agent',
  training: 'Training Agent',
  catalog: 'Catalog Agent',
  knowledge: 'Knowledge Agent',
}

function legacyDatasetForm(form) {
  const defaults = form?.defaults || {}
  return {
    ...form,
    form_type: 'dynamic_parameters',
    agent: 'dataset',
    purpose: 'dataset.add_samples',
    submit_label: '继续创建交接',
    fields: [
      { name: 'dataset_id', label: '草稿数据集 ID', type: 'integer', required: true, minimum: 1, default: defaults.dataset_id, placeholder: '例如：6' },
      { name: 'mode', label: '添加模式', type: 'select', required: true, default: defaults.mode || 'train_new', options: [
        { label: '新建商品训练图', value: 'train_new' },
        { label: '已有商品训练图', value: 'train_existing' },
        { label: 'val/test 结账场景', value: 'scene' },
      ] },
      { name: 'name', label: '商品名称', type: 'text', required: true, placeholder: '例如：可口可乐零度 500ml', visible_when: { field: 'mode', equals: 'train_new' } },
      { name: 'class_name', label: '类别英文名', type: 'text', required: true, placeholder: '例如：coca_cola_zero', visible_when: { field: 'mode', equals: 'train_new' } },
      { name: 'unit_price', label: '价格（元）', type: 'number', required: true, minimum: 0, step: 0.5, visible_when: { field: 'mode', equals: 'train_new' } },
      { name: 'barcode', label: '条码', type: 'text', required: false, visible_when: { field: 'mode', equals: 'train_new' } },
      { name: 'existing_product_id', label: '已有商品 ID', type: 'integer', required: true, minimum: 1, visible_when: { field: 'mode', equals: 'train_existing' } },
    ],
  }
}

const normalizedForm = computed(() => props.form.form_type === 'dataset_add_samples' ? legacyDatasetForm(props.form) : props.form)
const agentLabel = computed(() => agentNames[normalizedForm.value.agent] || '当前 Agent')
const visibleFields = computed(() => (normalizedForm.value.fields || []).filter((field) => {
  const rule = field.visible_when
  return !rule || values[rule.field] === rule.equals
}))

function hydrate(form) {
  Object.keys(values).forEach((key) => delete values[key])
  for (const field of form.fields || []) {
    if (field.default !== undefined && field.default !== null) values[field.name] = field.default
    else if (field.type === 'boolean') values[field.name] = false
    else if (field.type === 'multiselect') values[field.name] = []
    else values[field.name] = undefined
  }
  submitted.value = false
}

watch(normalizedForm, hydrate, { immediate: true, deep: true })

function isMissing(value) {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)
}

function numberInputProps(field) {
  const inputProps = {
    controls: false,
    step: Number.isFinite(field.step) ? field.step : 1,
  }
  if (Number.isFinite(field.minimum)) inputProps.min = field.minimum
  if (Number.isFinite(field.maximum)) inputProps.max = field.maximum
  if (field.type === 'integer') inputProps.precision = 0
  return inputProps
}

function submit() {
  const missing = visibleFields.value.find((field) => field.required && isMissing(values[field.name]))
  if (missing) return ElMessage.warning(`请填写${missing.label}`)
  const submittedValues = {}
  for (const field of visibleFields.value) {
    const value = values[field.name]
    submittedValues[field.name] = typeof value === 'string' ? value.trim() : value
  }
  submitted.value = true
  emit('submit', { form: normalizedForm.value, values: submittedValues })
}
</script>

<style lang="scss" scoped>
.agent-input-form { margin-top: 16px; padding: 17px; border: 1px solid rgba(124,58,237,.28); border-radius: 18px; background: linear-gradient(145deg,rgba(250,247,255,.96),rgba(255,255,255,.98)); box-shadow: 0 12px 30px rgba(76,29,149,.08); }.form-heading { display: flex; align-items: center; gap: 10px; }.form-mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 11px; color: #fff; background: linear-gradient(145deg,#8b5cf6,#6d28d9); }.form-heading div:last-child { display: flex; flex-direction: column; gap: 2px; }.form-heading span { color: #7c3aed; font-size: 10px; font-weight: 800; letter-spacing: .06em; }.form-heading strong { color: $text-primary; font-size: 14px; }.agent-input-form > p { margin: 12px 0; color: $text-secondary; font-size: 12px; line-height: 1.65; }.form-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 11px; margin-top: 13px; }.form-grid label { min-width: 0; display: flex; flex-direction: column; gap: 6px; }.form-grid label.wide { grid-column: 1/-1; }.form-grid label > span { color: $text-secondary; font-size: 11px; font-weight: 700; }.form-grid b { margin-left: 4px; color: #dc2626; font-size: 9px; }.form-grid em { margin-left: 4px; color: $text-placeholder; font-size: 9px; font-style: normal; font-weight: 500; }.form-grid small { color: $text-placeholder; font-size: 9px; line-height: 1.5; }.form-grid :deep(.el-input-number),.form-grid :deep(.el-select),.form-grid :deep(.el-date-editor) { width: 100%; }.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; padding-top: 13px; border-top: 1px solid rgba(124,58,237,.12); }.form-actions > span { color: $text-placeholder; font-size: 10px; line-height: 1.5; }.form-actions .el-button { flex: 0 0 auto; }.form-actions .el-button:not(.is-disabled) { background: #7c3aed; border-color: #7c3aed; }
@media (max-width:640px) { .form-grid { grid-template-columns:1fr; }.form-grid label.wide { grid-column:auto; }.form-actions { align-items:flex-start; flex-direction:column; }.form-actions .el-button { width:100%; } }
:global(html.dark .agent-input-form) { border-color:rgba(191,90,242,.3); background:linear-gradient(145deg,rgba(65,40,100,.4),rgba(44,44,46,.96)); box-shadow:0 14px 34px rgba(0,0,0,.28); }:global(html.dark .agent-input-form .form-heading strong) { color:#f5f5f7; }:global(html.dark .agent-input-form .form-actions) { border-color:rgba(255,255,255,.08); }
</style>
