import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  useVisionPetStore,
  VISION_PET_DEFAULT_SIZE,
  VISION_PET_PREFERENCES_KEY,
} from '@/stores/visionPet'

describe('visionPet preferences', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('persists visibility and normalized size preferences', () => {
    const store = useVisionPetStore()
    store.setVisible(false)
    store.setSizePercent(118)

    expect(JSON.parse(localStorage.getItem(VISION_PET_PREFERENCES_KEY))).toEqual({
      visible: false,
      sizePercent: 120,
    })

    setActivePinia(createPinia())
    const restoredStore = useVisionPetStore()
    expect(restoredStore.visible).toBe(false)
    expect(restoredStore.sizePercent).toBe(120)
  })

  it('resets preferences without mixing them into task state resets', () => {
    const store = useVisionPetStore()
    store.setVisible(false)
    store.setSizePercent(130)
    store.reset()

    expect(store.visible).toBe(false)
    expect(store.sizePercent).toBe(130)

    store.resetPreferences()
    expect(store.visible).toBe(true)
    expect(store.sizePercent).toBe(VISION_PET_DEFAULT_SIZE)
  })

  it('tracks concurrent tasks and aggregates the highest-priority visual state', () => {
    const store = useVisionPetStore()

    store.startTask({ id: 'task-a', message: '任务 A', state: 'working' })
    store.startTask({ id: 'task-b', message: '任务 B', state: 'working', progress: 20 })

    expect(store.tasks).toHaveLength(2)
    expect(store.state).toBe('working')

    store.notify({ state: 'error', message: '系统异常' })
    expect(store.state).toBe('error')

    store.clearMessage()
    expect(store.state).toBe('working')

    store.updateTask('task-b', { progress: 75 })
    expect(store.tasks.find((task) => task.id === 'task-b')?.progress).toBe(75)

    store.finishTask('task-a')
    store.finishTask('task-b')
    expect(store.tasks).toHaveLength(0)
    expect(store.state).toBe('idle')
  })
})
