import { describe, expect, it } from 'vitest'

import {
  annotationReviewSummary,
  attachFilesToStagedImages,
  buildDatasetProductCommitPayload,
} from '@/utils/datasetAnnotationReview'

const stage = {
  staging_token: 'a'.repeat(32),
  images: [
    {
      image_id: 'image-1',
      split: 'train',
      split_index: 0,
      filename: 'one.jpg',
      width: 100,
      height: 80,
      boxes: [],
      needs_review: true,
    },
    {
      image_id: 'image-2',
      split: 'val',
      split_index: 0,
      filename: 'two.jpg',
      width: 100,
      height: 80,
      boxes: [],
      needs_review: true,
    },
  ],
}

describe('dataset annotation review helpers', () => {
  it('matches staged images back to local files and preserves review state', () => {
    const files = { train: [{ name: 'one.jpg' }], val: [{ name: 'two.jpg' }], test: [] }
    const images = attachFilesToStagedImages(stage, files, (file) => `blob:${file.name}`)

    expect(images[0]).toMatchObject({ previewUrl: 'blob:one.jpg', reviewed: false, boxes: [] })
    expect(images[1]).toMatchObject({ previewUrl: 'blob:two.jpg', reviewed: false })
    expect(annotationReviewSummary(images)).toEqual({ total: 2, boxes: 0, missing: 2, pending: 2 })
  })

  it('builds a compact reviewed-box commit payload', () => {
    const images = attachFilesToStagedImages(
      stage,
      { train: [{ name: 'one.jpg' }], val: [{ name: 'two.jpg' }], test: [] },
      () => 'blob:test',
    )
    images[1].boxes = [{ x1: 4, y1: 5, x2: 60, y2: 70 }]
    images[1].reviewed = true
    const payload = buildDatasetProductCommitPayload(
      stage,
      { mode: 'train_new', name: ' Cola ', class_name: 'cola', unit_price: 3.5, barcode: '' },
      images,
    )

    expect(payload.name).toBe('Cola')
    expect(payload.class_name).toBe('cola')
    expect(payload.mode).toBe('train_new')
    expect(payload.barcode).toBeNull()
    expect(payload.images[1]).toEqual({
      image_id: 'image-2',
      reviewed: true,
      boxes: [{ x1: 4, y1: 5, x2: 60, y2: 70, product_id: null }],
    })
  })

  it('includes an existing product id on every scene box', () => {
    const images = attachFilesToStagedImages(
      stage,
      { train: [{ name: 'one.jpg' }], val: [{ name: 'two.jpg' }], test: [] },
      () => 'blob:test',
    )
    images[0].boxes = [{ x1: 1, y1: 2, x2: 20, y2: 30, product_id: 7 }]
    images[0].reviewed = true
    const payload = buildDatasetProductCommitPayload(
      stage,
      { mode: 'scene', name: '', class_name: '', unit_price: null, barcode: '' },
      images,
    )
    expect(payload.images[0].boxes[0].product_id).toBe(7)
    expect(payload.name).toBeNull()
  })
})
