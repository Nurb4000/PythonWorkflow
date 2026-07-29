import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { runApi } from '../services/api'

interface StepInstance {
  id: number
  step_id: number
  status: string
  input_data: any
  output_data: any
  error_message: string
  started_at: string
  completed_at: string
  position: number
}

interface Run {
  id: number
  workflow_id: number
  status: string
  triggered_by: string
  input_data: any
  output_data: any
  error_message: string
  started_at: string
  completed_at: string
  created_at: string
}

export const RunMonitor: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const runIdNum = parseInt(runId!)

  const { data: run, isLoading } = useQuery({
    queryKey: ['run', runIdNum],
    queryFn: async () => {
      // We need workflow_id to fetch the run, but we don't have it here
      // This is a simplified version - in production you'd pass workflow_id
      const response = await runApi.get(0, runIdNum)
      return response.data as Run
    },
    enabled: !!runId
  })

  const { data: steps } = useQuery({
    queryKey: ['run-steps', runIdNum],
    queryFn: async () => {
      const response = await runApi.getSteps(0, runIdNum)
      return response.data as StepInstance[]
    },
    enabled: !!runId
  })

  if (isLoading) {
    return <div className="loading">Loading run details...</div>
  }

  if (!run) {
    return <div className="error">Run not found</div>
  }

  const getStatusBadgeClass = (status: string) => {
    switch(status) {
      case 'completed': return 'badge-success'
      case 'failed': return 'badge-danger'
      case 'running': return 'badge-info'
      default: return 'badge-warning'
    }
  }

  const calculateDuration = (startedAt: string, completedAt: string) => {
    if (!startedAt || !completedAt) return '-'
    const start = new Date(startedAt).getTime()
    const end = new Date(completedAt).getTime()
    const seconds = Math.round((end - start) / 1000)
    
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  return (
    <div>
      <div className="card-header">
        <div>
          <h2>Run #{run.id}</h2>
          <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
            Workflow ID: {run.workflow_id} | Triggered by: {run.triggered_by}
          </p>
        </div>
        <Link to={`/workflows/${run.workflow_id}`} className="btn btn-secondary">
          Back to Workflow
        </Link>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">
            <span className={`badge ${getStatusBadgeClass(run.status)}`}>
              {run.status}
            </span>
          </div>
          <div className="stat-label">Status</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {calculateDuration(run.started_at, run.completed_at)}
          </div>
          <div className="stat-label">Duration</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: '1rem' }}>
            {new Date(run.created_at).toLocaleString()}
          </div>
          <div className="stat-label">Created</div>
        </div>
      </div>

      {run.error_message && (
        <div className="error">
          <strong>Error:</strong> {run.error_message}
        </div>
      )}

      <div className="card">
        <h3 className="card-title">Input Data</h3>
        <pre style={{ 
          background: '#f8f9fa', 
          padding: '1rem', 
          borderRadius: '4px',
          overflow: 'auto',
          maxHeight: '300px'
        }}>
          {JSON.stringify(run.input_data, null, 2)}
        </pre>
      </div>

      <div className="card">
        <h3 className="card-title">Output Data</h3>
        <pre style={{ 
          background: '#f8f9fa', 
          padding: '1rem', 
          borderRadius: '4px',
          overflow: 'auto',
          maxHeight: '300px'
        }}>
          {JSON.stringify(run.output_data, null, 2)}
        </pre>
      </div>

      <div className="card">
        <h3 className="card-title">Step Instances</h3>
        {steps && steps.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Position</th>
                <th>Status</th>
                <th>Started</th>
                <th>Completed</th>
                <th>Duration</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step: StepInstance) => (
                <tr key={step.id}>
                  <td>{step.position}</td>
                  <td>
                    <span className={`badge ${getStatusBadgeClass(step.status)}`}>
                      {step.status}
                    </span>
                  </td>
                  <td>{step.started_at ? new Date(step.started_at).toLocaleTimeString() : '-'}</td>
                  <td>{step.completed_at ? new Date(step.completed_at).toLocaleTimeString() : '-'}</td>
                  <td>
                    {step.started_at && step.completed_at 
                      ? calculateDuration(step.started_at, step.completed_at)
                      : '-'
                    }
                  </td>
                  <td style={{ color: step.error_message ? '#e74c3c' : 'inherit' }}>
                    {step.error_message || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No step instances found</p>
        )}
      </div>
    </div>
  )
}
