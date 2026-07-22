import { computed, ref } from 'vue'

const SUPPORTED_POSES = new Set([
  'idle',
  'awakening',
  'recognition',
  'team',
  'relay',
  'training',
  'core',
  'happy',
])

export function useVisionState() {
  const pose = ref('idle')
  const setPose = (nextPose = 'idle') => {
    pose.value = SUPPORTED_POSES.has(nextPose) ? nextPose : 'idle'
  }

  return {
    pose: computed(() => pose.value),
    setPose,
    reset: () => setPose('idle'),
  }
}
