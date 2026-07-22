import { describe, expect, it } from 'vitest'
import { JOURNEY_CHAPTER_RANGES, resolveJourneyProgress } from '@/composables/useScrollDriver'

describe('Vision Journey scroll progress', () => {
  it('moves out of the first chapter after the shortened opening range', () => {
    expect(JOURNEY_CHAPTER_RANGES[0]).toEqual({ start: 0, end: 0.18 })
    expect(resolveJourneyProgress(0.17).chapterIndex).toBe(0)
    expect(resolveJourneyProgress(0.18).chapterIndex).toBe(1)
  })

  it('returns continuous local progress for each chapter', () => {
    const opening = resolveJourneyProgress(0.09)
    const recognition = resolveJourneyProgress(0.37)
    const team = resolveJourneyProgress(0.78)

    expect(opening.chapterProgress).toBeCloseTo(0.5)
    expect(recognition.chapterProgress).toBeCloseTo(0.5)
    expect(team.chapterProgress).toBeCloseTo(0.5)
  })

  it('clamps progress at both ends', () => {
    expect(resolveJourneyProgress(-1)).toMatchObject({
      chapterIndex: 0,
      chapterProgress: 0,
      progress: 0,
    })
    expect(resolveJourneyProgress(2)).toMatchObject({
      chapterIndex: 2,
      chapterProgress: 1,
      progress: 1,
    })
  })
})
