import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'

import AgentInputFormCard from '@/components/AgentInputFormCard.vue'

const stubs = {
  ElIcon: { template: '<span><slot /></span>' },
  EditPen: { template: '<i />' },
  ElInput: { props: ['modelValue'], template: '<input :value="modelValue" />' },
  ElInputNumber: { props: ['modelValue'], template: '<input :value="modelValue" />' },
  ElSelect: { props: ['modelValue'], template: '<select><slot /></select>' },
  ElOption: { template: '<option />' },
  ElSwitch: { props: ['modelValue'], template: '<input type="checkbox" :checked="modelValue" />' },
  ElDatePicker: { props: ['modelValue'], template: '<input :value="modelValue" />' },
  ElButton: {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

describe('AgentInputFormCard', () => {
  it('accepts typing in a real Element Plus integer input', async () => {
    const wrapper = mount(AgentInputFormCard, {
      props: {
        form: {
          form_type: 'dynamic_parameters',
          form_id: 'catalog-form-1',
          agent: 'catalog',
          title: '查询数据集价目表',
          purpose: 'catalog.list_prices',
          fields: [
            {
              name: 'dataset_version_id', label: '数据集版本 ID', type: 'integer',
              required: true, minimum: 1, maximum: null, step: null,
            },
          ],
        },
      },
      global: { plugins: [ElementPlus] },
    })

    const input = wrapper.get('.el-input-number input')
    await input.setValue('2')

    expect(input.element.value).toBe('2')
  })

  it('renders a generic schema and emits structured values', async () => {
    const form = {
      form_type: 'dynamic_parameters',
      form_id: 'form-1',
      agent: 'training',
      title: '补充训练参数',
      purpose: 'training.start',
      submit_label: '生成训练预览',
      fields: [
        { name: 'epochs', label: '训练轮数', type: 'integer', required: true, default: 100 },
        {
          name: 'optimizer', label: '优化器', type: 'select', required: true, default: 'SGD',
          options: [{ label: 'SGD', value: 'SGD' }],
        },
      ],
    }
    const wrapper = mount(AgentInputFormCard, { props: { form }, global: { stubs } })

    expect(wrapper.text()).toContain('补充训练参数')
    expect(wrapper.text()).toContain('训练轮数')
    expect(wrapper.text()).toContain('Training Agent')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('submit')[0][0]).toEqual({
      form,
      values: { epochs: 100, optimizer: 'SGD' },
    })
  })

  it('hides conditional fields that do not match the selected mode', () => {
    const wrapper = mount(AgentInputFormCard, {
      props: {
        form: {
          form_type: 'dynamic_parameters',
          agent: 'dataset',
          title: '补充样品参数',
          fields: [
            {
              name: 'mode', label: '模式', type: 'select', default: 'scene',
              options: [{ label: '场景', value: 'scene' }],
            },
            {
              name: 'name', label: '商品名称', type: 'text', required: true,
              visible_when: { field: 'mode', equals: 'train_new' },
            },
          ],
        },
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('模式')
    expect(wrapper.text()).not.toContain('商品名称')
  })
})
