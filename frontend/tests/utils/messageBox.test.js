import { beforeEach, describe, expect, it, vi } from 'vitest'

const { confirm } = vi.hoisted(() => ({
  confirm: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm },
}))

import { confirmAction, isMessageBoxDismissal } from '@/utils/messageBox'

describe('message box confirmation', () => {
  beforeEach(() => {
    confirm.mockReset()
  })

  it('returns true after the user confirms', async () => {
    confirm.mockResolvedValue('confirm')

    await expect(confirmAction('确认操作？', '操作确认')).resolves.toBe(true)
  })

  it.each(['cancel', 'close'])('treats %s as a normal dismissal', async (action) => {
    confirm.mockRejectedValue(action)

    expect(isMessageBoxDismissal(action)).toBe(true)
    await expect(confirmAction('确认操作？', '操作确认')).resolves.toBe(false)
  })

  it('rethrows unexpected errors', async () => {
    const error = new Error('message box failed')
    confirm.mockRejectedValue(error)

    await expect(confirmAction('确认操作？', '操作确认')).rejects.toBe(error)
  })
})
