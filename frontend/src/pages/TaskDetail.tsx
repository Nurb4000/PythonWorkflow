import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { taskApi, dateTargetsApi } from '../services/api'
import { useAuth } from '../components/Auth'
import { FormRenderer } from '../components/FormRenderer'
import { DateTargetBadge, DateTargetInfo, pickRunTarget } from '../components/DateTargetBadge'

interface Task {
  id: number
  workflow_run_id: number | null
  step_id: number | null
  title: string
  description: string
  status: string
  assigned_to_user_id: number | null
  assigned_group_id: number | null
  form_id: number | null
  task_data: any
  result_data: any
  pause_state?: string
  assigned_user?: { id: number; username: string; full_name: string } | null
  assigned_group?: { id: number; name: string } | null
  created_at: string
  updated_at: string
  completed_at: string | null
  closed_at: string | null
}

export const TaskDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const taskId = parseInt(id!)
  
  const [resultData, setResultData] = useState<any>({})
  const [rejectReason, setRejectReason] = useState('')
  const [showRawData, setShowRawData] = useState(false)

  const { data: task, isLoading } = useQuery({
    queryKey: ['task', taskId],
    queryFn: async () => {
      const response = await taskApi.getTask(taskId)
      return response.data as Task
    },
    enabled: !!id
  })

  const [pauseState, setPauseState] = useState(task?.pause_state || 'in_process')

  const pauseMutation = useMutation({
    mutationFn: (state: string) => taskApi.pauseTask(taskId, state),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: () => taskApi.resumeTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })

  const { data: runDateTargets } = useQuery({
    queryKey: ['date-targets', 'run', task?.workflow_run_id],
    queryFn: async () => {
      const response = await dateTargetsApi.list({ run_id: task!.workflow_run_id! })
      return (response.data || []) as DateTargetInfo[]
    },
    enabled: !!task?.workflow_run_id
  })

  const runTarget = useMemo(() => pickRunTarget(runDateTargets), [runDateTargets])

  const takeMutation = useMutation({
    mutationFn: () => taskApi.takeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', taskId] })
  })

  const completeMutation = useMutation({
    mutationFn: (resultData: any) => taskApi.completeTask(taskId, resultData || {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', taskId] })
  })

  const rejectMutation = useMutation({
    mutationFn: () => taskApi.rejectTask(taskId, rejectReason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', taskId] })
  })

  const closeMutation = useMutation({
    mutationFn: () => taskApi.closeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', taskId] })
  })

  const formInitialData = useMemo(
    () => ({ ...(task?.task_data || {}), ...(task?.result_data || {}) }),
    [task?.task_data, task?.result_data]
  )

  if (isLoading) {
    return <div className="loading">Loading task...</div>
  }

  if (!task) {
    return <div className="error">Task not found</div>
  }

  const userGroupIds = user?.groups?.map((g: { id: number }) => g.id) || []

  const canTake = task.status === 'open' && 
    (task.assigned_to_user_id === user?.id || 
     (task.assigned_group_id != null && userGroupIds.includes(task.assigned_group_id)) ||
     user?.role === 'admin')
  
  const canComplete = task.status === 'owned' && 
    (task.assigned_to_user_id === user?.id || user?.role === 'admin')

  const canEditForm = canComplete
  
  const canReject = (task.status === 'owned' || task.status === 'completed') && 
    (task.assigned_to_user_id === user?.id || user?.role === 'admin')
  
  const canClose = task.status === 'completed' && 
    ['admin', 'developer', 'staff'].includes(user?.role || '')

  return (
    <div>
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ margin: 0 }}>{task.title}</h2>
          <span className={`badge ${task.status === 'open' ? 'badge-warning' : 
            task.status === 'review' ? 'badge-info' : 
            task.status === 'owned' ? 'badge-primary' : 
            task.status === 'completed' ? 'badge-success' : 'badge-secondary'}`}>
            {task.status}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.85rem', color: '#666' }}>SLA/OLA Pause:</label>
          {pauseState === 'in_process' ? (
            <select
              className="form-input"
              value={pauseState}
              onChange={(e) => setPauseState(e.target.value)}
              style={{ maxWidth: '250px' }}
            >
              <option value="pending_customer_feedback">Pending Customer Feedback</option>
              <option value="scheduled_with_customer">Scheduled with Customer</option>
              <option value="pending_vendor">Pending Vendor</option>
              <option value="pending_internal_team">Pending Internal Team</option>
              <option value="in_process">In Process</option>
              <option value="scheduled">Scheduled</option>
            </select>
          ) : (
            <span className="badge badge-warning">{pauseState.replace(/_/g, ' ')}</span>
          )}
          {pauseState !== 'in_process' && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
            >
              {resumeMutation.isPending ? 'Resuming...' : 'Resume'}
            </button>
          )}
          {pauseState === 'in_process' && (
            <button
              className="btn btn-sm btn-primary"
              onClick={() => pauseMutation.mutate(pauseState)}
              disabled={pauseMutation.isPending || pauseState === 'in_process'}
            >
              {pauseMutation.isPending ? 'Pausing...' : 'Set Pause'}
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">Details</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <strong>Assigned To:</strong> {task.assigned_user?.full_name || task.assigned_user?.username || 'Unassigned'}
          </div>
          <div>
            <strong>Group:</strong> {task.assigned_group?.name || '-'}
          </div>
          <div>
            <strong>Workflow Run:</strong> {task.workflow_run_id ? <Link to={`/runs/${task.workflow_run_id}`}>#{task.workflow_run_id}</Link> : '-'}
          </div>
          {runTarget && (
            <div>
              <strong>Date Target:</strong> <DateTargetBadge target={runTarget} />
            </div>
          )}
          <div>
            <strong>Created:</strong> {new Date(task.created_at).toLocaleString()}
          </div>
          {task.completed_at && (
            <div>
              <strong>Completed:</strong> {new Date(task.completed_at).toLocaleString()}
            </div>
          )}
        </div>
        
        {task.description && (
          <div style={{ marginTop: '1rem' }}>
            <strong>Description:</strong>
            <p>{task.description}</p>
          </div>
        )}

        {(Object.keys(task.task_data).length > 0 || Object.keys(task.result_data).length > 0) && (
          <div style={{ marginTop: '1rem' }}>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setShowRawData(!showRawData)}
              style={{ marginBottom: showRawData ? '0.5rem' : 0 }}
            >
              {showRawData ? '▾ Hide Raw Data' : '▸ Show Raw Data (Task/Result JSON)'}
            </button>
            {showRawData && (
              <>
                {Object.keys(task.task_data).length > 0 && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <strong>Task Data:</strong>
                    <pre style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px', overflow: 'auto' }}>
                      {JSON.stringify(task.task_data, null, 2)}
                    </pre>
                  </div>
                )}
                {Object.keys(task.result_data).length > 0 && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <strong>Result Data:</strong>
                    <pre style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px', overflow: 'auto' }}>
                      {JSON.stringify(task.result_data, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {task.form_id && (
        <div className="card">
          <h3 className="card-title">Form</h3>
          <p style={{ color: '#7f8c8d', marginBottom: '1rem' }}>
            {canEditForm
              ? 'Fill out the form below and submit to complete this task.'
              : task.status === 'open'
                ? 'Take this task to fill out the form.'
                : 'Saved form data is shown below (read-only).'}
          </p>
          <FormRenderer
            key={`${task.form_id}-${task.status}-${task.completed_at || task.updated_at || ''}`}
            formId={task.form_id}
            readOnly={!canEditForm}
            initialData={formInitialData}
            onSubmitData={canEditForm ? (data) => completeMutation.mutate(data) : undefined}
            submitLabel="Complete Task & Save Data"
          />
        </div>
      )}

      <div className="card">
        <h3 className="card-title">Actions</h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {canTake && (
            <button
              className="btn btn-primary"
              onClick={() => takeMutation.mutate()}
              disabled={takeMutation.isPending}
            >
              Take Task
            </button>
          )}
          
          {canComplete && !task.form_id && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Result data (JSON)"
                value={JSON.stringify(resultData, null, 2)}
                onChange={(e) => {
                  try {
                    setResultData(JSON.parse(e.target.value))
                  } catch {
                    // Ignore invalid JSON
                  }
                }}
                style={{ width: '300px' }}
              />
              <button
                className="btn btn-success"
                onClick={() => completeMutation.mutate(resultData)}
                disabled={completeMutation.isPending}
              >
                Complete Task
              </button>
            </div>
          )}

          {canReject && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Rejection reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                style={{ width: '200px' }}
              />
              <button
                className="btn btn-danger"
                onClick={() => rejectMutation.mutate()}
                disabled={rejectMutation.isPending}
              >
                Reject
              </button>
            </div>
          )}

          {canClose && (
            <button
              className="btn btn-secondary"
              onClick={() => closeMutation.mutate()}
              disabled={closeMutation.isPending}
            >
              Close Task
            </button>
          )}
        </div>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Link to="/admin/tasks" className="btn btn-secondary">← Back to Tasks</Link>
      </div>
    </div>
  )
}
