import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DatasetBoxEditor from '@/components/dataset/DatasetBoxEditor.vue'

describe('DatasetBoxEditor', () => {
  it('renders reviewed boxes and allows clearing them for redraw', async () => {
    const wrapper = mount(DatasetBoxEditor, {
      props: {
        modelValue: [
          { x1: 10, y1: 12, x2: 80, y2: 70 },
          { x1: 82, y1: 20, x2: 110, y2: 60 },
        ],
        imageUrl: 'blob:test-product',
        imageWidth: 120,
        imageHeight: 80,
      },
      global: {
        stubs: {
          ElButton: {
            props: ['disabled'],
            emits: ['click'],
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
          },
        },
      },
    })

    expect(wrapper.find('svg').attributes('viewBox')).toBe('0 0 120 80')
    expect(wrapper.findAll('.annotation-box')).toHaveLength(2)
    await wrapper.get('button:nth-of-type(2)').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual([[]])
    expect(wrapper.emitted('change')).toHaveLength(1)
  })
})
