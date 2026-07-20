import { ElMessageBox } from 'element-plus'

export function isMessageBoxDismissal(action) {
  return action === 'cancel' || action === 'close'
}

export async function confirmAction(message, title, options = {}) {
  try {
    await ElMessageBox.confirm(message, title, options)
    return true
  } catch (action) {
    if (isMessageBoxDismissal(action)) return false
    throw action
  }
}
