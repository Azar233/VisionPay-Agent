import request from '@/utils/request'

export const getStatistics = (days = 30) =>
  request.get('/dashboard/statistics', { params: { days } })
export const getTrend = ({ days = 30, hours, bucketHours } = {}) =>
  request.get('/dashboard/trend', {
    params: { days, ...(hours ? { hours, bucket_hours: bucketHours || 1 } : {}) },
  })
export const getClassDistribution = (days = 30) =>
  request.get('/dashboard/class-dist', { params: { days } })
export const getSceneDistribution = (days = 30) =>
  request.get('/dashboard/scene-dist', { params: { days } })
export const getTypeDistribution = (days = 30) =>
  request.get('/dashboard/type-dist', { params: { days } })
export const getModelUsage = (days = 30, limit = 8, { hours, bucketHours } = {}) =>
  request.get('/dashboard/model-usage', {
    params: { days, limit, ...(hours ? { hours, bucket_hours: bucketHours || 1 } : {}) },
  })
