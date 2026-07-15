const IMAGE_SUFFIX_RE = /\.(?:jpe?g|png|bmp|webp|tiff?)$/i

const SPLIT_ALIASES = {
  train: new Set(['train', 'training']),
  val: new Set(['val', 'valid', 'validation']),
  test: new Set(['test', 'testing']),
}

function relativePath(file) {
  return String(file.webkitRelativePath || file.name || '').replaceAll('\\', '/')
}

function explicitSplit(file) {
  const directories = relativePath(file).split('/').slice(0, -1)
  for (const directory of directories) {
    const normalized = directory.toLowerCase()
    for (const [split, aliases] of Object.entries(SPLIT_ALIASES)) {
      if (aliases.has(normalized)) return split
    }
  }
  return null
}

function isImage(file) {
  return String(file.type || '').startsWith('image/') || IMAGE_SUFFIX_RE.test(file.name || '')
}

export function partitionProductFolderFiles(fileList) {
  const allFiles = Array.from(fileList || [])
  const images = allFiles
    .filter(isImage)
    .sort((left, right) => relativePath(left).localeCompare(relativePath(right), undefined, { numeric: true }))
  const folderName = relativePath(images[0]).split('/')[0] || ''
  const files = { train: [], val: [], test: [] }
  const hasExplicitSplit = images.some((file) => explicitSplit(file))

  if (hasExplicitSplit) {
    for (const file of images) files[explicitSplit(file) || 'train'].push(file)
  } else if (images.length < 3) {
    files.train.push(...images)
  } else {
    const valCount = Math.max(1, Math.round(images.length * 0.1))
    const testCount = Math.max(1, Math.round(images.length * 0.1))
    const trainCount = images.length - valCount - testCount
    files.train.push(...images.slice(0, trainCount))
    files.val.push(...images.slice(trainCount, trainCount + valCount))
    files.test.push(...images.slice(trainCount + valCount))
  }

  return {
    files,
    folderName,
    ignoredCount: allFiles.length - images.length,
    splitMode: hasExplicitSplit ? 'directory' : 'automatic',
    totalBytes: images.reduce((sum, file) => sum + Number(file.size || 0), 0),
    totalImages: images.length,
  }
}
