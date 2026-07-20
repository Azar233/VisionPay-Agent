export function attachFilesToStagedImages(
  stage,
  filesBySplit,
  createObjectUrl = (file) => URL.createObjectURL(file),
) {
  const pairs = (stage?.images || []).map((item) => {
    const file = filesBySplit[item.split]?.[item.split_index]
    if (!file) throw new Error(`找不到暂存图片对应的本地文件：${item.filename}`)
    return { item, file }
  })
  return pairs.map(({ item, file }) => {
    return {
      ...item,
      file,
      previewUrl: createObjectUrl(file),
      boxes: [],
      reviewed: false,
      edited: false,
    }
  })
}

export function buildDatasetProductCommitPayload(stage, product, images) {
  return {
    staging_token: stage.staging_token,
    mode: product.mode,
    existing_product_id:
      product.mode === 'train_existing' ? Number(product.existing_product_id) : null,
    name: product.mode === 'train_new' ? product.name.trim() : null,
    class_name: product.mode === 'train_new' ? product.class_name.trim() : null,
    unit_price: product.mode === 'train_new' ? Number(product.unit_price) : null,
    barcode: product.barcode?.trim() || null,
    images: images.map((item) => ({
      image_id: item.image_id,
      reviewed: Boolean(item.reviewed),
      boxes: item.boxes.map(({ x1, y1, x2, y2, product_id }) => ({
        x1,
        y1,
        x2,
        y2,
        product_id: product.mode === 'scene' ? Number(product_id) : null,
      })),
    })),
  }
}

export function annotationReviewSummary(images) {
  return images.reduce(
    (summary, item) => {
      summary.total += 1
      summary.boxes += item.boxes.length
      if (!item.boxes.length) summary.missing += 1
      if (!item.reviewed) summary.pending += 1
      return summary
    },
    { total: 0, boxes: 0, missing: 0, pending: 0 },
  )
}
