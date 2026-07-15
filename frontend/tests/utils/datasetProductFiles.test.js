import { describe, expect, it } from 'vitest'

import { partitionProductFolderFiles } from '@/utils/datasetProductFiles'

function file(path, size = 100) {
  return {
    name: path.split('/').at(-1),
    webkitRelativePath: path,
    type: 'image/jpeg',
    size,
  }
}

describe('partitionProductFolderFiles', () => {
  it('preserves explicit train, val, and test directories', () => {
    const result = partitionProductFolderFiles([
      file('cola/test/c.jpg'),
      file('cola/train/a.jpg'),
      file('cola/validation/b.jpg'),
    ])

    expect(result.splitMode).toBe('directory')
    expect(result.folderName).toBe('cola')
    expect(result.files.train.map((item) => item.name)).toEqual(['a.jpg'])
    expect(result.files.val.map((item) => item.name)).toEqual(['b.jpg'])
    expect(result.files.test.map((item) => item.name)).toEqual(['c.jpg'])
  })

  it('uses a deterministic 80/10/10 split for a flat folder', () => {
    const files = Array.from({ length: 10 }, (_, index) => file(`cola/${index + 1}.jpg`))
    const result = partitionProductFolderFiles(files)

    expect(result.splitMode).toBe('automatic')
    expect(result.files.train).toHaveLength(8)
    expect(result.files.val).toHaveLength(1)
    expect(result.files.test).toHaveLength(1)
  })

  it('ignores non-image files and keeps very small folders train-only', () => {
    const textFile = { name: 'notes.txt', webkitRelativePath: 'cola/notes.txt', type: 'text/plain', size: 20 }
    const result = partitionProductFolderFiles([file('cola/a.jpg'), textFile])

    expect(result.totalImages).toBe(1)
    expect(result.ignoredCount).toBe(1)
    expect(result.files.train).toHaveLength(1)
    expect(result.files.val).toHaveLength(0)
    expect(result.files.test).toHaveLength(0)
  })
})
