export const CHAT_ATTACHMENT_MAX_COUNT = 30

const CHAT_ATTACHMENT_PATTERN = /\.(jpe?g|png|bmp|webp|zip|mp4|avi|mov|mkv)$/i

export function chatAttachmentKey(file) {
  return [file?.name || '', Number(file?.size || 0), Number(file?.lastModified || 0), file?.type || ''].join('::')
}

export function prepareChatAttachmentAdditions(currentItems, fileList, maxCount = CHAT_ATTACHMENT_MAX_COUNT) {
  const existingKeys = new Set((currentItems || []).map((item) => chatAttachmentKey(item.file)))
  const additions = []
  let unsupportedCount = 0
  let duplicateCount = 0
  let overflowCount = 0

  for (const file of Array.from(fileList || [])) {
    if (!CHAT_ATTACHMENT_PATTERN.test(file.name || '')) {
      unsupportedCount += 1
      continue
    }

    const key = chatAttachmentKey(file)
    if (existingKeys.has(key)) {
      duplicateCount += 1
      continue
    }

    if ((currentItems?.length || 0) + additions.length >= maxCount) {
      overflowCount += 1
      continue
    }

    existingKeys.add(key)
    additions.push(file)
  }

  return { additions, unsupportedCount, duplicateCount, overflowCount }
}
