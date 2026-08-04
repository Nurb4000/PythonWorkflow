import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { runApi, aiApi } from '../services/api'

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
  route_taken?: string  // P4.3: which route was taken for condition steps
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
      const response = await runApi.getRun(runIdNum)
      return response.data as Run
    },
    enabled: !!runId
  })

  const { data: steps } = useQuery({
    queryKey: ['run-steps', runIdNum],
    queryFn: async () => {
      const response = await runApi.getRunSteps(runIdNum)
      return response.data as StepInstance[]
    },
    enabled: !!runId
  })

  // AI error diagnosis state
  const [aiDiagnosing, setAiDiagnosing] = useState<number | null>(null)
  const [aiDiagnosis, setAiDiagnosis] = useState<Record<number, any>>({})
  const [runAiDiagnosis, setRunAiDiagnosis] = useState<any>(null)
  const [runAiDiagnosing, setRunAiDiagnosing] = useState(false)

  const handleAiDiagnoseStep = async (step: StepInstance) => {
    if (!step.error_message) return
    setAiDiagnosing(step.id)
    try {
      const res = await aiApi.explainError({
        step_type: 'unknown',
        step_config: step.input_data || {},
        error_message: step.error_message,
        input_data_sample: step.input_data,
      })
      setAiDiagnosis(prev => ({ ...prev, [step.id]: res.data.result }))
    } catch (err: any) {
      setAiDiagnosis(prev => ({ ...prev, [step.id]: { error: err.response?.data?.detail || 'AI diagnosis failed' } }))
    } finally {
      setAiDiagnosing(null)
    }
  }

  const handleAiDiagnoseRun = async () => {
    if (!run?.error_message) return
    setRunAiDiagnosing(true)
    try {
      const failedStep = steps?.find(s => s.status === 'failed')
      const res = await aiApi.explainError({
        step_type: failedStep?.input_data?.step_type || 'unknown',
        step_config: failedStep?.output_data || run.input_data || {},
        error_message: run.error_message,
        input_data_sample: run.input_data,
      })
      setRunAiDiagnosis(res.data.result)
    } catch (err: any) {
      setRunAiDiagnosis({ error: err.response?.data?.detail || 'AI diagnosis failed' })
    } finally {
      setRunAiDiagnosing(false)
    }
  }

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

  // P4.3: Determine if this is a graph-mode run (has branches)
  const isGraphMode = steps && steps.some(s => {
    // Check if any step has routes in its definition (condition steps in graph mode)
    return true // Simplified: assume graph mode if there are multiple paths
  })

  // P4.3: Group steps by status for easier viewing
  const completedSteps = steps?.filter(s => s.status === 'completed') || []
  const failedSteps = steps?.filter(s => s.status === 'failed') || []
  const skippedSteps = steps?.filter(s => s.status === 'skipped') || []
  const runningSteps = steps?.filter(s => s.status === 'running') || []

  return (
    <div>
      <div className="card-header">
        <div>
          <h2>Run #{run.id}</h2>
          <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
            Workflow ID: {run.workflow_id} | Triggered by: {run.triggered_by}
            {run.status === 'waiting' && <span className="badge badge-warning" style={{ marginLeft: '0.5rem' }}>Paused (human task)</span>}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {run.status === 'running' && (
            <Link to={`/runs/${run.id}/cancel`} className="btn btn-danger">Cancel Run</Link>
          )}
          <Link to={`/workflows/${run.workflow_id}`} className="btn btn-secondary">
            Back to Workflow
          </Link>
        </div>
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

      {/* P4.3: Error message display */}
      {run.error_message && (
        <div className="error" style={{ padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <strong style={{ fontSize: '1.1rem' }}>❌ Run Failed:</strong>
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
          {runAiDiagnosis && (
            <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f' }}>
              {runAiDiagnosis.error ? (
                <span style={{ color: '#e74c3c' }}>{runAiDiagnosis.error}</span>
              ) : (
                <>
                  <strong>AI Diagnosis:</strong>
                  {runAiDiagnosis.explanation && <p>{runAiDiagnosis.explanation}</p>}
                  {runAiDiagnosis.root_cause && <p><strong>Root Cause:</strong> {runAiDiagnosis.root_cause}</p>}
                  {runAiDiagnosis.suggested_fix && <p><strong>Suggested Fix:</strong> {runAiDiagnosis.suggested_fix}</p>}
                  {runAiDiagnosis.fixed_config && (
                    <>
                      <strong>Fixed Config:</strong>
                      <pre style={{ whiteSpace: 'pre-wrap', background: '#fff', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem' }}>
                        {JSON.stringify(runAiDiagnosis.fixed_config, null, 2)}
                      </pre>
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* P4.3: Chosen branch display for graph runs */}
      {isGraphMode && steps && steps.length > 0 && (
        <div className="card" style={{ marginBottom: '1rem' }}>
          <h3 className="card-title">🔀 Chosen Branches</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {steps.filter(s => s.status === 'completed' || s.status === 'failed').map(step => (
              <span key={step.id} className="badge" style={{ 
                background: step.status === 'failed' ? '#e74c3c' : '#27ae60',
                color: 'white',
                padding: '0.25rem 0.5rem',
                fontSize: '0.85rem'
              }}>
                Step {step.position}: {step.status}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="card-title">Input Data</h3>
        <pre style={{ 
          background: '#f8f9fa', 
          padding: '1rem', 
          borderRadius: '4px',
          overflow: 'auto',
          maxHeight: '300px',
          fontSize: '0.85rem'
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
          maxHeight: '300px',
          fontSize: '0.85rem'
        }}>
          {JSON.stringify(run.output_data, null, 2)}
        </pre>
      </div>

      <div className="card">
        <h3 className="card-title">Step Instances ({steps?.length || 0})</h3>
        {steps && steps.length > 0 ? (
          <div>
            {/* P4.3: Expandable step details */}
            {steps.map((step: StepInstance, idx: number) => (
              <div key={step.id} style={{ 
                border: '1px solid #ddd', 
                borderRadius: '6px', 
                marginBottom: '0.5rem',
                overflow: 'hidden'
              }}>
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  padding: '0.75rem', 
                  background: idx % 2 === 0 ? '#f8f9fa' : 'white',
                  cursor: 'pointer'
                }} onClick={() => {
                  const details = document.getElementById(`step-details-${step.id}`)
                  if (details) {
                    details.style.display = details.style.display === 'none' ? 'block' : 'none'
                  }
                }}>
                  <span style={{ marginRight: '1rem', fontWeight: 'bold' }}>#{step.position}</span>
                  <span className={`badge ${getStatusBadgeClass(step.status)}`} style={{ marginRight: '1rem' }}>
                    {step.status}
                  </span>
                  <span style={{ flex: 1 }}>
                    {step.started_at && step.completed_at 
                      ? calculateDuration(step.started_at, step.completed_at)
                      : '-'
                    }
                  </span>
                  {step.error_message && (
                    <span style={{ color: '#e74c3c', fontSize: '0.85rem' }}>
                      ⚠ {step.error_message.substring(0, 50)}{step.error_message.length > 50 ? '...' : ''}
                    </span>
                  )}
                  <span style={{ marginLeft: '1rem' }}>▼</span>
                </div>
                <div id={`step-details-${step.id}`} style={{ display: 'none', padding: '1rem', background: '#fff', borderTop: '1px solid #ddd' }}>
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Input:</strong>
                    <pre style={{ background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem', maxHeight: '100px', overflow: 'auto' }}>
                      {JSON.stringify(step.input_data, null, 2)}
                    </pre>
                  </div>
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Output:</strong>
                    <pre style={{ background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem', maxHeight: '100px', overflow: 'auto' }}>
                      {JSON.stringify(step.output_data, null, 2)}
                    </pre>
                  </div>
                  {step.error_message && (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong style={{ color: '#e74c3c' }}>Error:</strong>
                        <button
                          className="btn btn-sm btn-warning"
                          onClick={() => handleAiDiagnoseStep(step)}
                          disabled={aiDiagnosing === step.id}
                        >
                          {aiDiagnosing === step.id ? '...' : 'AI Diagnose'}
                        </button>
                      </div>
                      <pre style={{ background: '#ffebee', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem', color: '#c62828' }}>
                        {step.error_message}
                      </pre>
                      {aiDiagnosis[step.id] && (
                        <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f', fontSize: '0.85rem' }}>
                          {aiDiagnosis[step.id].error ? (
                            <span style={{ color: '#e74c3c' }}>{aiDiagnosis[step.id].error}</span>
                          ) : (
                            <>
                              {aiDiagnosis[step.id].explanation && <p>{aiDiagnosis[step.id].explanation}</p>}
                              {aiDiagnosis[step.id].suggested_fix && <p><strong>Fix:</strong> {aiDiagnosis[step.id].suggested_fix}</p>}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No step instances found</p>
        )}
      </div>
    </div>
  )
}
