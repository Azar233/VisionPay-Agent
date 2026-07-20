import { describe, expect, it } from 'vitest'

import {
  CHAT_ATTACHMENT_MAX_COUNT,
  chatAttachmentKey,
  prepareChatAttachmentAdditions,
} from '@/utils/chatAttachments'

function image(name, options = {}) {
  return new File(['image'], name, {
    type: options.type || 'image/jpeg',
    lastModified: options.lastModified || 1,
  })
}

describe('chat attachment queue', () => {
  it('adds several images selected in one operation', () => {
    const files = [image('one.jpg'), image('two.png', { type: 'image/png' })]
    const result = prepareChatAttachmentAdditions([], files)

    expect(result.additions).toEqual(files)
    expect(result.unsupportedCount).toBe(0)
  })

  it('appends a later selection without replacing existing attachments', () => {
    const first = image('first.jpg')
    const second = image('second.jpg')
    const current = [{ id: chatAttachmentKey(first), file: first, preview: 'blob:first' }]
    const result = prepareChatAttachmentAdditions(current, [second])

    expect(current.map((item) => item.file.name)).toEqual(['first.jpg'])
    expect(result.additions.map((file) => file.name)).toEqual(['second.jpg'])
  })

  it('ignores duplicates and unsupported files', () => {
    const first = image('first.jpg')
    const current = [{ id: chatAttachmentKey(first), file: first }]
    const result = prepareChatAttachmentAdditions(current, [first, image('notes.txt')])

    expect(result.additions).toEqual([])
    expect(result.duplicateCount).toBe(1)
    expect(result.unsupportedCount).toBe(1)
  })

  it('enforces the cumulative attachment limit', () => {
    const current = Array.from({ length: CHAT_ATTACHMENT_MAX_COUNT - 1 }, (_, index) => {
      const file = image(`current-${index}.jpg`)
      return { id: chatAttachmentKey(file), file }
    })
    const result = prepareChatAttachmentAdditions(current, [
      image('accepted.jpg'),
      image('overflow.jpg'),
    ])

    expect(result.additions.map((file) => file.name)).toEqual(['accepted.jpg'])
    expect(result.overflowCount).toBe(1)
  })
})
