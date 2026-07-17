import request from '@/utils/request'

export const getTaskList = (params) => request.get('/history/tasks', { params })
export const getTaskDetail = (taskId) => request.get(`/history/tasks/${taskId}`)
export const deleteTask = (taskId) => request.delete(`/history/tasks/${taskId}`)
export const getHistorySummary = () => request.get('/history/summary')
export const getScenes = () => request.get('/history/scenes')
export const getHistoryOverview = () => request.get('/history/overview')
export const getAgentCallList = (params) => request.get('/history/agent-calls', { params })
export const getAgentCallDetail = (messageId) => request.get(`/history/agent-calls/${messageId}`)
export const getModelHistoryList = (params) => request.get('/history/models', { params })
export const getModelHistoryDetail = (modelId) => request.get(`/history/models/${modelId}`)
