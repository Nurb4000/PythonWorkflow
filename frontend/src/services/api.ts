import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Workflow APIs
export const workflowApi = {
  list: () => api.get('/workflows/'),
  get: (id: number) => api.get(`/workflows/${id}`),
  create: (data: any) => api.post('/workflows/', data),
  update: (id: number, data: any) => api.put(`/workflows/${id}`, data),
  delete: (id: number) => api.delete(`/workflows/${id}`),
  addStep: (workflowId: number, stepData: any) => 
    api.post(`/workflows/${workflowId}/steps`, stepData),
  triggerRun: (workflowId: number, data: any) => 
    api.post(`/workflows/${workflowId}/run`, data)
}

// Workflow Run APIs
export const runApi = {
  list: (workflowId: number) => api.get(`/workflows/${workflowId}/runs/`),
  get: (workflowId: number, runId: number) => 
    api.get(`/workflows/${workflowId}/runs/${runId}`),
  getSteps: (workflowId: number, runId: number) => 
    api.get(`/workflows/${workflowId}/runs/${runId}/steps`),
  cancel: (workflowId: number, runId: number) => 
    api.delete(`/workflows/${workflowId}/runs/${runId}`)
}

// Admin APIs
export const adminApi = {
  getStats: (workflowId?: number, days?: number) => 
    api.get('/admin/stats', { params: { workflow_id: workflowId, days } }),
  listRuns: (params?: any) => 
    api.get('/admin/runs', { params }),
  getAuditLog: (workflowId: number) => 
    api.get(`/admin/workflows/${workflowId}/audit-log`),
  listSchedules: () => api.get('/admin/schedules'),
  createSchedule: (data: any) => api.post('/admin/schedules', data),
  updateSchedule: (id: number, data: any) => api.put(`/admin/schedules/${id}`, data),
  deleteSchedule: (id: number) => api.delete(`/admin/schedules/${id}`)
}

// AI APIs
export const aiApi = {
  generateStep: (description: string, context?: any) => 
    api.post('/ai/generate-step', null, { params: { description, context } }),
  generateForm: (description: string) => 
    api.post('/ai/generate-form', null, { params: { description } })
}

export default api
