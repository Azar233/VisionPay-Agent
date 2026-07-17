export const VISION_PET_TASK_EVENT = 'visionpay:pet-task'

/**
 * Frontend event bridge for the VisionPay pet.
 * A future SSE/WebSocket handler can call this function for every task update.
 */
export function notifyVisionPetTask(detail = {}) {
  window.dispatchEvent(new CustomEvent(VISION_PET_TASK_EVENT, { detail }))
}
