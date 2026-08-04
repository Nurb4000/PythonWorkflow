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

// Handle expired/invalid tokens: clear credentials and redirect to login
// (skips the login endpoint itself so failed password attempts still show an error)
const handleUnauthorized = (error: any) => {
  if (error.response?.status === 401) {
    const url = error.config?.url || ''
    if (!url.includes('/auth/login') && !url.includes('/auth/me')) {
      localStorage.removeItem('token')
      delete api.defaults.headers.common['Authorization']
      delete axios.defaults.headers.common['Authorization']
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
  }
  return Promise.reject(error)
}

api.interceptors.response.use((response) => response, handleUnauthorized)

// Workflow APIs
export const workflowApi = {
  list: () => api.get('/workflows/'),
  get: (id: number) => api.get(`/workflows/${id}`),
  create: (data: any) => api.post('/workflows/', data),
  update: (id: number, data: any) => api.put(`/workflows/${id}`, data),
  delete: (id: number) => api.delete(`/workflows/${id}`),
  setPermissions: (id: number, groupIds: number[]) =>
    api.put(`/workflows/${id}/permissions`, groupIds),
  addStep: (workflowId: number, stepData: any) => 
    api.post(`/workflows/${workflowId}/steps`, stepData),
  updateStep: (workflowId: number, stepId: number, stepData: any) =>
    api.put(`/workflows/${workflowId}/steps/${stepId}`, stepData),
  deleteStep: (workflowId: number, stepId: number) =>
    api.delete(`/workflows/${workflowId}/steps/${stepId}`),
  triggerRun: (workflowId: number, data: any) => 
    api.post(`/workflows/${workflowId}/run`, data)
}

// Auth / user / group APIs
export const authApi = {
  listUsers: () => api.get('/auth/users'),
  createUser: (data: any) => {
    const { custom_data, ...params } = data
    return api.post('/auth/register', custom_data || {}, { params })
  },
  updateUser: (id: number, data: any) => {
    const { custom_data, ...params } = data
    return api.put(`/auth/users/${id}`, custom_data || {}, { params })
  },
  deleteUser: (id: number) => api.delete(`/auth/users/${id}`),
  listGroups: () => api.get('/auth/groups'),
  createGroup: (data: any) => api.post('/auth/groups', null, { params: data }),
  updateGroup: (id: number, data: any) => api.put(`/auth/groups/${id}`, null, { params: data }),
  deleteGroup: (id: number) => api.delete(`/auth/groups/${id}`),
  setUserGroups: (userId: number, groupIds: number[]) =>
    api.put(`/auth/users/${userId}/groups`, groupIds)
}

// Workflow Run APIs
export const runApi = {
  list: (workflowId: number) => api.get(`/workflows/${workflowId}/runs/`),
  get: (workflowId: number, runId: number) => 
    api.get(`/workflows/${workflowId}/runs/${runId}`),
  getSteps: (workflowId: number, runId: number) => 
    api.get(`/workflows/${workflowId}/runs/${runId}/steps`),
  cancel: (workflowId: number, runId: number) => 
    api.delete(`/workflows/${workflowId}/runs/${runId}`),
  getRun: (runId: number) => api.get(`/runs/${runId}`),
  getRunSteps: (runId: number) => api.get(`/runs/${runId}/steps`)
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

// Portal APIs
export const portalApi = {
  listWorkflows: () => api.get('/portal/workflows'),
  runWorkflow: (workflowId: number, inputData: any = {}) =>
    api.post(`/portal/workflows/${workflowId}/run`, inputData),
  myRuns: () => api.get('/portal/my-runs'),
  myTasks: () => api.get('/portal/my-tasks')  // P3.3
}

// Task APIs
export const taskApi = {
  listTasks: (params?: any) => api.get('/tasks', { params }),
  getTask: (taskId: number) => api.get(`/tasks/${taskId}`),
  openTask: (taskId: number) => api.post(`/tasks/${taskId}/open`),
  reviewTask: (taskId: number) => api.post(`/tasks/${taskId}/review`),
  takeTask: (taskId: number) => api.post(`/tasks/${taskId}/take`),
  completeTask: (taskId: number, resultData?: any) => 
    api.post(`/tasks/${taskId}/complete`, resultData || {}),
  closeTask: (taskId: number) => api.post(`/tasks/${taskId}/close`),
  rejectTask: (taskId: number, reason?: string) => 
    api.post(`/tasks/${taskId}/reject`, {}, { params: { reason } }),
  updateTask: (taskId: number, data: any) => api.put(`/tasks/${taskId}`, data),
  deleteTask: (taskId: number) => api.delete(`/tasks/${taskId}`)
}

// AI APIs
export const aiApi = {
  generateStep: (description: string, context?: any) =>
    api.post('/ai/generate-step', null, { params: { description, context } }),
  generateForm: (description: string) =>
    api.post('/ai/generate-form', null, { params: { description } }),
  assistNode: (body: { action: string; step_type: string; description?: string; current_config?: any; upstream_data_shapes?: any; error_message?: string }) =>
    api.post('/ai/assist-node', body),
  assistQuery: (body: { action: string; description?: string; sql?: string; table?: string; error_message?: string; available_columns?: any[] }) =>
    api.post('/ai/assist-query', body),
  assistForm: (body: { action: string; description?: string; current_schema?: any }) =>
    api.post('/ai/assist-form', body),
  explainError: (body: { step_type: string; step_config: any; error_message: string; input_data_sample?: any }) =>
    api.post('/ai/explain-error', body),
}

// Custom Fields APIs
export const dataFieldApi = {
  list: (params?: any) => api.get('/data-fields/', { params }),
  get: (id: number) => api.get(`/data-fields/${id}`),
  create: (data: any) => api.post('/data-fields/', data),
  update: (id: number, data: any) => api.put(`/data-fields/${id}`, data),
  delete: (id: number) => api.delete(`/data-fields/${id}`),
}

// Data Query APIs
export const dataQueryApi = {
  listTables: () => api.get('/data-query/tables'),
  runVisual: (body: any) => api.post('/data-query/build', body),
  runSql: (body: any) => api.post('/data-query/sql', body),
  updateCustomData: (table: string, recordId: number, data: any) =>
    api.put(`/data-query/records/${table}/${recordId}/custom-data`, data),
  bulkUpdateCustomData: (data: any) => api.post('/data-query/bulk-update/custom-data', data),
}

// Data Export APIs
export const dataExportApi = {
  exportTable: (tableName: string, params?: any) =>
    api.get(`/data-export/table/${tableName}`, { params, responseType: 'blob' }),
  exportQuery: (body: any) =>
    api.post('/data-export/query', body, { responseType: 'blob' }),
}

// SQL Views APIs
export const sqlViewApi = {
  list: () => api.get('/sql-views/'),
  create: (data: { name: string; definition_sql: string; description?: string }) => api.post('/sql-views/', null, { params: data }),
  update: (id: number, data: any) => api.put(`/sql-views/${id}`, null, { params: data }),
  delete: (id: number) => api.delete(`/sql-views/${id}`),
}

// Workflow Import/Export APIs
export const workflowExportApi = {
  export: (workflowId: number, format: string = 'xml') =>
    api.get(`/workflows/${workflowId}/export`, { params: { fmt: format }, responseType: 'blob' }),
  import: (fileContent: string, filename: string, options?: any) =>
    api.post('/workflows/import-body', { file_content: fileContent, filename, ...options }),
  duplicate: (workflowId: number, newName?: string) =>
    api.post(`/workflows/${workflowId}/duplicate`, null, { params: { new_name: newName } }),
  listDemos: () => api.get('/workflows/demo-list'),
  getDemo: (filename: string) =>
    api.get(`/workflows/demo/${filename}`, { responseType: 'blob' }),
}

export default api
