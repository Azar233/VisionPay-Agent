export const VISION_PET_TASK_EVENT = 'visionpay:pet-task'

const WORKING_TASK_STATUSES = new Set(['pending', 'queued', 'running', 'processing', 'streaming'])
const AGENT_LABELS = {
  catalog: '商品',
  dataset: '数据集',
  detection: '检测',
  knowledge: '知识',
  training: '训练',
}

const activeTasks = new Map()
let taskSequence = 0

/**
 * Frontend event bridge for the VisionPay pet.
 * A future SSE/WebSocket handler can call this function for every task update.
 */
export function notifyVisionPetTask(detail = {}) {
  window.dispatchEvent(new CustomEvent(VISION_PET_TASK_EVENT, { detail }))
}

/**
 * Adapter for future backend task updates received through SSE or WebSocket.
 * Active task statuses animate the working sequence; terminal statuses return
 * the pet to idle unless the backend explicitly supplies another pet state.
 */
export function notifyVisionPetTaskProgress({ status = '', state, ...detail } = {}) {
  const normalizedStatus = String(status).toLowerCase()
  notifyVisionPetTask({
    ...detail,
    status,
    state: state || (WORKING_TASK_STATUSES.has(normalizedStatus) ? 'working' : 'idle'),
  })
}

function latestActiveTask() {
  return [...activeTasks.values()].at(-1)
}

/**
 * Create a lifecycle lease for a real backend task. The pet only returns to
 * idle after every active lease has finished, which prevents overlapping
 * requests from resetting each other's working state.
 */
export function beginVisionPetTask({ id, message = '正在处理任务' } = {}) {
  const taskId = id || `pet-task-${++taskSequence}`
  const task = { id: taskId, message: String(message || '正在处理任务') }
  activeTasks.set(taskId, task)
  notifyVisionPetTaskProgress({ status: 'running', message: task.message, duration: 0 })

  let finished = false
  return Object.freeze({
    id: taskId,
    update(nextMessage) {
      if (finished || !activeTasks.has(taskId) || !nextMessage) return
      task.message = String(nextMessage)
      notifyVisionPetTaskProgress({ status: 'running', message: task.message, duration: 0 })
    },
    finish({ message: finalMessage = '', duration = 0 } = {}) {
      if (finished) return
      finished = true
      activeTasks.delete(taskId)
      const remainingTask = latestActiveTask()
      if (remainingTask) {
        notifyVisionPetTaskProgress({ status: 'running', message: remainingTask.message, duration: 0 })
        return
      }
      notifyVisionPetTaskProgress({ status: 'completed', message: finalMessage, duration })
    },
  })
}

/** Update a task lease from the events already emitted by /api/chat/stream. */
export function updateVisionPetTaskFromWorkflow(task, event = {}) {
  if (!task || !event?.type) return
  if (event.type === 'routing') {
    const agent = AGENT_LABELS[event.agent] || event.agent || 'Agent'
    task.update(`${agent}智能体正在处理`)
  } else if (event.type === 'tool_call') {
    task.update(`正在执行 ${event.tool || '任务工具'}`)
  } else if (event.type === 'tool_result') {
    task.update('正在整理执行结果')
  } else if (event.type === 'text_chunk') {
    task.update('正在组织回复')
  }
}
