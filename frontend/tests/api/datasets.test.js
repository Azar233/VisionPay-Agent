import { beforeEach, describe, expect, it, vi } from 'vitest'

const { request } = vi.hoisted(() => ({
  request: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/request', () => ({ default: request }))

import {
  createDatasetVersionApi,
  freezeDatasetVersionApi,
  getDatasetVersionApi,
  getDatasetVersionsApi,
  setCurrentDatasetVersionApi,
  updateDatasetVersionApi,
  validateDatasetVersionApi,
} from '@/api/datasets'

describe('dataset API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists and reads dataset versions', () => {
    getDatasetVersionsApi({ status: 'draft' })
    getDatasetVersionApi(12)
    expect(request.get).toHaveBeenNthCalledWith(1, '/datasets', {
      params: { status: 'draft' },
    })
    expect(request.get).toHaveBeenNthCalledWith(2, '/datasets/12')
  })

  it('creates and updates drafts', () => {
    const payload = { version: 'v1' }
    createDatasetVersionApi(payload)
    updateDatasetVersionApi(7, payload)
    expect(request.post).toHaveBeenCalledWith('/datasets', payload)
    expect(request.put).toHaveBeenCalledWith('/datasets/7', payload)
  })

  it('passes the explicit filesystem check flag', () => {
    validateDatasetVersionApi(3, true)
    freezeDatasetVersionApi(3, false)
    expect(request.post).toHaveBeenNthCalledWith(1, '/datasets/3/validate', {
      check_filesystem: true,
    })
    expect(request.post).toHaveBeenNthCalledWith(2, '/datasets/3/freeze', {
      check_filesystem: false,
    })
  })

  it('sets a ready version as current', () => {
    setCurrentDatasetVersionApi(9)
    expect(request.post).toHaveBeenCalledWith('/datasets/9/set-current')
  })
})
