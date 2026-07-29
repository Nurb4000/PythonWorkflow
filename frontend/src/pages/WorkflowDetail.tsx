import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { workflowApi, runApi } from '../services/api'

interface Workflow {
  id: number
  name: string
  description: string
  is_active: boolean
  steps: any[]
}

interface Run {
  id: number
  status: string
  triggered_by: string
  started_at: string
  completed_at: string
  error_message: string
}

export const WorkflowDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const workflowId = parseInt(id!)

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      const response = await workflowApi.get(workflowId)
      return response.data
    },
    enabled: !!id
  })

  const { data: runs } = useQuery({
    queryKey: ['runs', workflowId],
    queryFn: async () => {
      const response = await runApi.list(workflowId)
      return response.data
    },
    enabled: !!id
  })

  const triggerRunMutation = useMutation({
    mutationFn: (inputData: any) => 
      workflowApi.triggerRun(workflowId, { input_data: inputData }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs', workflowId] })
    }
  })

  if (isLoading) {
    return <div className="loading">Loading workflow...</div>
  }

  if (!workflow) {
    return <div className="error">Workflow not found</div>
  }

  return (
    <div>
      <div className="card-header">
        <div>
          <h2>{workflow.name}</h2>
          <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>{workflow.description}</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Link to={`/workflows/${workflowId}/design`} className="btn btn-primary">
            Edit Workflow
          </Link>
          <button 
            className="btn btn-success"
            onClick={() => triggerRunMutation.mutate({})}
            disabled={triggerRunMutation.isPending}
          >
            {triggerRunMutation.isPending ? 'Running...' : '▶ Run Now'}
          </button>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{workflow.steps?.length || 0}</div>
          <div className="stat-label">Steps</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            <span className={`badge ${workflow.is_active ? 'badge-success' : 'badge-danger'}`}>
              {workflow.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <div className="stat-label">Status</div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">Workflow Steps</h3>
        {workflow.steps && workflow.steps.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Type</th>
                <th>Configuration</th>
                <th>Condition</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {workflow.steps.map((step: any, index: number) => (
                <tr key={step.id}>
                  <td>{step.position}</td>
                  <td>
                    <span className={`step-type step-type-${step.step_type}`}>
                      {step.step_type}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                    {JSON.stringify(step.definition).substring(0, 100)}...
                  </td>
                  <td>{step.condition_expr || '-'}</td>
                  <td>
                    <span className={`badge ${step.is_enabled ? 'badge-success' : 'badge-danger'}`}>
                      {step.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No steps defined. <Link to={`/workflows/${workflowId}/design`}>Design workflow</Link></p>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">Recent Runs</h3>
        {runs && runs.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Triggered By</th>
                <th>Started</th>
                <th>Completed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run: Run) => (
                <tr key={run.id}>
                  <td>#{run.id}</td>
                  <td>
                    <span className={`badge badge-${
                      run.status === 'completed' ? 'success' : 
                      run.status === 'failed' ? 'danger' : 
                      run.status === 'running' ? 'info' : 'warning'
                    }`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{run.triggered_by}</td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</td>
                  <td>{run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}</td>
                  <td>
                    <Link to={`/runs/${run.id}`} className="btn btn-sm btn-primary">
                      View Details
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No runs yet. Click "Run Now" to execute.</p>
        )}
      </div>
    </div>
  )
}
