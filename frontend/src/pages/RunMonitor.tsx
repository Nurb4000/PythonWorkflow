import React, { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { runApi, aiApi } from '../services/api'
import { useAuth } from '../components/Auth'
import { WorkflowDesigner } from './WorkflowDesigner'

export const RunMonitor: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const runIdNum = parseInt(runId!)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canManage = user?.role === 'admin' || user?.role === 'developer'
  const [searchParams] = useSearchParams()
  const focusStepId = searchParams.get('focus') ? parseInt(searchParams.get('focus')!) : undefined

  // Determine if run is still active (for polling)
  const isActiveStatus = (status: string) => ['running', 'waiting', 'pending'].includes(status)

  // Fetch inspector data — single call for everything
  const { data: inspector, isLoading } = useQuery({
    queryKey: ['run-inspector', runIdNum],
    queryFn: async () => {
      const response = await runApi.getInspector(runIdNum)
      return response.data
    },
    enabled: !!runId,
    refetchInterval: (query) => {
      // Poll every 3s while the run is active
      const data = query.state.data
      if (data && isActiveStatus(data.run?.status)) {
        return 3000
      }
      return false
    },
  })

  const run = inspector?.run
  const steps = inspector?.steps || []
  const workflow = inspector?.workflow

  // Stats
  const completedSteps = steps.filter((s: any) => s.status === 'completed')
  const failedSteps = steps.filter((s: any) => s.status === 'failed')
  const runningSteps = steps.filter((s: any) => s.status === 'running')
  const skippedSteps = steps.filter((s: any) => s.status === 'skipped')

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: () => runApi.cancelGlobal(runIdNum),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['run-inspector', runIdNum] })
      queryClient.invalidateQueries({ queryKey: ['admin-runs'] })
    },
  })

  // Re-run mutation
  const rerunMutation = useMutation({
    mutationFn: () => runApi.rerun(runIdNum),
    onSuccess: (data) => {
      const newRunId = data.data.id
      queryClient.invalidateQueries({ queryKey: ['admin-runs'] })
      navigate(`/runs/${newRunId}`)
    },
  })

  // AI error diagnosis for the run-level error
  const [runAiDiagnosing, setRunAiDiagnosing] = useState(false)
  const [runAiDiagnosis, setRunAiDiagnosis] = useState<any>(null)
  const [runAiError, setRunAiError] = useState('')

  const handleAiDiagnoseRun = useCallback(async () => {
    if (!run?.error_message) return
    setRunAiDiagnosing(true)
    setRunAiError('')
    setRunAiDiagnosis(null)
    try {
      const failedStep = steps.find((s: any) => s.status === 'failed')
      const res = await aiApi.explainError({
        step_type: failedStep?.step_type || 'unknown',
        step_config: failedStep?.custom_data || run.input_data || {},
        error_message: run.error_message,
        input_data_sample: run.input_data,
      })
      setRunAiDiagnosis(res.data.result)
    } catch (err: any) {
      setRunAiError(err.response?.data?.detail || 'AI diagnosis failed')
    } finally {
      setRunAiDiagnosing(false)
    }
  }, [run, steps])

  // Helpers
  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed': return 'badge-success'
      case 'failed': return 'badge-danger'
      case 'running': return 'badge-info'
      case 'waiting': return 'badge-warning'
      case 'cancelled': return 'badge-secondary'
      default: return 'badge-warning'
    }
  }

  const calculateDuration = (startedAt?: string, completedAt?: string) => {
    if (!startedAt || !completedAt) return '-'
    const start = new Date(startedAt).getTime()
    const end = new Date(completedAt).getTime()
    const seconds = Math.round((end - start) / 1000)
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  if (isLoading) {
    return <div className="loading">Loading run details...</div>
  }

  if (!run) {
    return <div className="error">Run not found</div>
  }

  // Find first failed step for focus
  const firstFailedStepId = failedSteps[0]?.step_id

  return (
    <div>
      {/* Stats cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">
            <span className={`badge ${getStatusBadgeClass(run.status)}`}>
              {run.status}
            </span>
            {isActiveStatus(run.status) && (
              <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: '#2980b9' }}>
                ⟳ polling...
              </span>
            )}
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
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>
            {completedSteps.length}
          </div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: '1.2rem', color: failedSteps.length > 0 ? '#e74c3c' : 'inherit' }}>
            {failedSteps.length}
          </div>
          <div className="stat-label">Failed</div>
        </div>
      </div>

      {/* Run-level error */}
      {run.error_message && (
        <div className="error" style={{ padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <strong style={{ fontSize: '1.1rem' }}>Run Failed:</strong>
            <button
              className="btn btn-sm btn-warning"
              onClick={handleAiDiagnoseRun}
              disabled={runAiDiagnosing}
            >
              {runAiDiagnosing ? 'Diagnosing...' : 'AI Diagnose'}
            </button>
          </div>
          <pre style={{ marginTop: '0.5rem', background: '#fff', padding: '0.75rem', borderRadius: '4px', border: '1px solid #e74c3c' }}>
            {run.error_message}
          </pre>
          {runAiError && <div style={{ marginTop: '0.5rem', color: '#e74c3c' }}>{runAiError}</div>}
          {runAiDiagnosis && (
            <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f' }}>
              <strong>AI Diagnosis:</strong>
              {runAiDiagnosis.explanation && <p>{runAiDiagnosis.explanation}</p>}
              {runAiDiagnosis.root_cause && <p><strong>Root Cause:</strong> {runAiDiagnosis.root_cause}</p>}
              {runAiDiagnosis.suggested_fix && <p><strong>Suggested Fix:</strong> {runAiDiagnosis.suggested_fix}</p>}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {canManage && (run.status === 'running' || run.status === 'pending') && (
          <button
            className="btn btn-danger"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
          >
            {cancelMutation.isPending ? 'Cancelling...' : 'Cancel Run'}
          </button>
        )}
        {canManage && run.workflow_id != null && (
          <button
            className="btn btn-info"
            onClick={() => rerunMutation.mutate()}
            disabled={rerunMutation.isPending}
          >
            {rerunMutation.isPending ? 'Re-running...' : 'Re-run with same input'}
          </button>
        )}
        {canManage && run.workflow_id != null && (
          <Link to={`/workflows/${run.workflow_id}`} className="btn btn-secondary">
            Back to Workflow
          </Link>
        )}
        {firstFailedStepId && !focusStepId && (
          <Link to={`/runs/${run.id}?focus=${firstFailedStepId}`} className="btn btn-warning">
            Jump to first failure
          </Link>
        )}
      </div>

      {/* Graph view — WorkflowDesigner in readOnly mode */}
      {inspector && (
        <WorkflowDesigner
          readOnly
          inspectorData={inspector}
          focusStepId={focusStepId || firstFailedStepId}
        />
      )}

      {/* Collapsible raw details fallback */}
      <details style={{ marginTop: '1rem' }}>
        <summary style={{ cursor: 'pointer', fontWeight: 'bold', padding: '0.5rem 0' }}>
          Raw Details (Input / Output / Step List)
        </summary>

        <div className="card" style={{ marginTop: '0.5rem' }}>
          <h3 className="card-title">Input Data</h3>
          <pre style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '4px', overflow: 'auto', maxHeight: '300px', fontSize: '0.85rem' }}>
            {JSON.stringify(run.input_data, null, 2)}
          </pre>
        </div>

        <div className="card" style={{ marginTop: '0.5rem' }}>
          <h3 className="card-title">Output Data</h3>
          <pre style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '4px', overflow: 'auto', maxHeight: '300px', fontSize: '0.85rem' }}>
            {JSON.stringify(run.output_data, null, 2)}
          </pre>
        </div>

        <div className="card" style={{ marginTop: '0.5rem' }}>
          <h3 className="card-title">Step Instances ({steps.length})</h3>
          {steps.length > 0 ? (
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Title</th>
                  <th>Duration</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {steps.map((step: any) => (
                  <tr key={step.id}>
                    <td>{step.position}</td>
                    <td><span className={`badge ${getStatusBadgeClass(step.status)}`}>{step.status}</span></td>
                    <td>{step.step_type}</td>
                    <td>{step.title || '-'}</td>
                    <td>{step.duration_seconds != null ? `${step.duration_seconds.toFixed(3)}s` : '-'}</td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
      </details>
    </div>
  )
}
