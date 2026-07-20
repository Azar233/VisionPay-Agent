const ACTIVE_FROZEN_STATUSES = new Set(['pending_train', 'training', 'published'])
const DERIVABLE_STATUSES = new Set([...ACTIVE_FROZEN_STATUSES, 'archived'])

export function isDatasetDraft(status) {
  return status === 'draft'
}

export function canArchiveDataset(status) {
  return ACTIVE_FROZEN_STATUSES.has(status)
}

export function canDeriveDataset(status) {
  return DERIVABLE_STATUSES.has(status)
}
