import request from '@/utils/request'

export const getUserList = (params) => request.get('/user/list', { params })
export const getRoles = () => request.get('/user/roles')
export const updateProfile = (data) => request.put('/user/profile', data)
export const getAgentInstructions = () => request.get('/user/agent-instructions')
export const updateAgentInstructions = (instructions) =>
  request.put('/user/agent-instructions', { instructions })
export const uploadAvatar = (data) =>
  request.post('/user/avatar', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const changePassword = (data) => request.put('/user/password', data)
export const getCustomerModePasswordStatus = () => request.get('/user/customer-mode-password')
export const updateCustomerModePassword = (password) =>
  request.put('/user/customer-mode-password', { password })
export const verifyCustomerModePassword = (password) =>
  request.post('/user/customer-mode-password/verify', { password }, { skipGlobalError: true })
