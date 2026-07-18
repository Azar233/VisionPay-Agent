import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeSourcesCard from '@/components/KnowledgeSourcesCard.vue'


describe('KnowledgeSourcesCard', () => {
  it('shows structured sources and expands retrieval details', async () => {
    const wrapper = mount(KnowledgeSourcesCard, {
      props: {
        payload: {
          forced: true,
          has_knowledge: true,
          retrievals: [
            {
              collection: 'knowledge',
              rewritten_query: 'Dataset 数据集冻结条件和影响范围',
            },
          ],
          sources: [
            {
              id: 'chunk-1',
              collection: 'knowledge',
              source: 'dataset/dataset_lifecycle.md',
              title: 'dataset lifecycle',
              domain: 'dataset',
              similarity: 0.876,
              rank: 1,
              excerpt: '冻结后数据集内容只读。',
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('参考知识 1')
    expect(wrapper.find('.sources-summary').attributes('aria-expanded')).toBe('false')

    await wrapper.find('.sources-summary').trigger('click')

    expect(wrapper.find('.sources-summary').attributes('aria-expanded')).toBe('true')
    expect(wrapper.text()).toContain('Dataset 数据集冻结条件和影响范围')
    expect(wrapper.text()).toContain('dataset/dataset_lifecycle.md')
    expect(wrapper.text()).toContain('88%')
    expect(wrapper.text()).toContain('冻结后数据集内容只读。')
  })

  it('shows a grounded empty state when no result passes the threshold', async () => {
    const wrapper = mount(KnowledgeSourcesCard, {
      props: {
        payload: {
          forced: true,
          has_knowledge: false,
          retrievals: [{ collection: 'knowledge', rewritten_query: '无匹配问题' }],
          sources: [],
        },
      },
    })

    expect(wrapper.text()).toContain('未找到可靠参考资料')
    await wrapper.find('.sources-summary').trigger('click')
    expect(wrapper.text()).toContain('没有片段达到相似度阈值')
  })
})
