import { describe, expect, it } from 'vitest'

import {
  canArchiveDataset,
  canDeriveDataset,
  isDatasetDraft,
} from '@/utils/datasetLifecycle'

describe('dataset lifecycle actions', () => {
  it.each([
    ['draft', true, false, false],
    ['pending_train', false, true, true],
    ['training', false, true, true],
    ['published', false, true, true],
    ['archived', false, false, true],
  ])('maps %s to the expected action set', (status, draft, archive, derive) => {
    expect(isDatasetDraft(status)).toBe(draft)
    expect(canArchiveDataset(status)).toBe(archive)
    expect(canDeriveDataset(status)).toBe(derive)
  })
})

