import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { adminApi, runApi, aiApi } from '../services/api'
import { RunsTable, ColumnDef } from '../components/RunsTable'

interface Run {
  id: number
  workflow_id: number | null
  workflow_name: string
  status: string
  triggered_by: string
  started_at: string
  completed_at: string
  created_at: string
  error_message: string
  steps_total: number
  steps_completed: number
  steps_failed: number
  steps_running: number
  steps_pending: number
  steps_skipped: number
}

type Tab = 'active' | 'completed' | 'all'

const TERMINAL = ['completed', 'failed', 'cancelled']
const ACTIVE_STATUSES = ['pending', 'running']

export const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case 'completed': return 'badge-success'
    case 'failed': return 'badge-danger'
    case 'running': return 'badge-info'
    case 'pending': return 'badge-warning'
    default: return 'badge-warning'
  }
}

export const formatDuration = (startedAt: string, completedAt: string) => {
  if (!startedAt || !completedAt) return '-'
  const start = new Date(startedAt).getTime()
  const end = new Date(completedAt).getTime()
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

export const WorkflowRunsAdmin: React.FC = () => {
  const [tab, setTab] = useState<Tab>('active')
  const [workflowFilter, setWorkflowFilter] = useState<string>('')
  const [aiDiagnosing, setAiDiagnosing] = useState<number | null>(null)
  const [aiDiagnosis, setAiDiagnosis] = useState<Record<number, any>>({})
  const queryClient = useQueryClient()

  const { data: runs, isLoading } = useQuery({
    queryKey: ['admin-runs-all'],
    queryFn: async () => {
      const response = await adminApi.listRuns({ limit: 1000 })
      return response.data as Run[]
    }
  })

  const cancelMutation = useMutation({
    mutationFn: (run: Run) => runApi.cancel(run.workflow_id!, run.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-runs-all'] })
  })

  const handleAiDiagnose = async (run: Run) => {
    if (!run.error_message) return
    setAiDiagnosing(run.id)
    try {
      const res = await aiApi.explainError({
        step_type: 'unknown',
        step_config: {},
        error_message: run.error_message,
        input_data_sample: {},
      })
      setAiDiagnosis(prev => ({ ...prev, [run.id]: res.data.result }))
    } catch (err: any) {
      setAiDiagnosis(prev => ({ ...prev, [run.id]: { error: err.response?.data?.detail || 'AI diagnosis failed' } }))
    } finally {
      setAiDiagnosing(null)
    }
  }

  const workflows = useMemo(() => {
    const map = new Map<number, string>()
    ;(runs || []).forEach(r => {
      if (r.workflow_id != null && !map.has(r.workflow_id)) map.set(r.workflow_id, r.workflow_name || `#${r.workflow_id}`)
    })
    return Array.from(map.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([id, name]) => ({ id, name }))
  }, [runs])

  const filtered = useMemo(() => {
    let list = runs || []
    if (tab === 'active') list = list.filter(r => ACTIVE_STATUSES.includes(r.status))
    else if (tab === 'completed') list = list.filter(r => TERMINAL.includes(r.status))
    if (workflowFilter) list = list.filter(r => r.workflow_id === Number(workflowFilter))
    return list
  }, [runs, tab, workflowFilter])

  const columns: ColumnDef[] = useMemo(() => [
    {
      key: 'id',
      label: 'ID',
      csv: r => String(r.id)
    },
    {
      key: 'workflow',
      label: 'Workflow',
      render: r => r.workflow_id
        ? <Link to={`/workflows/${r.workflow_id}`}>{r.workflow_name || `#${r.workflow_id}`}</Link>
        : <span>{r.workflow_name || 'Unknown workflow'}</span>,
      csv: r => r.workflow_name || (r.workflow_id ? `#${r.workflow_id}` : 'Unknown workflow')
    },
    {
      key: 'status',
      label: 'Status',
      render: r => <span className={`badge ${getStatusBadgeClass(r.status)}`}>{r.status}</span>,
      csv: r => r.status
    },
    {
      key: 'triggered_by',
      label: 'Triggered By',
      csv: r => r.triggered_by || ''
    },
    {
      key: 'steps',
      label: 'Steps',
      render: r => `${r.steps_completed}/${r.steps_total}`,
      csv: r => `${r.steps_completed}/${r.steps_total}`
    },
    {
      key: 'started_at',
      label: 'Started',
      render: r => r.started_at ? new Date(r.started_at).toLocaleString() : '-',
      csv: r => r.started_at || ''
    },
    {
      key: 'completed_at',
      label: 'Completed',
      render: r => r.completed_at ? new Date(r.completed_at).toLocaleString() : '-',
      csv: r => r.completed_at || ''
    },
    {
      key: 'duration',
      label: 'Duration',
      render: r => formatDuration(r.started_at, r.completed_at),
      csv: r => formatDuration(r.started_at, r.completed_at)
    },
    {
      key: 'error_message',
      label: 'Error',
      render: r => (
        <div style={{ maxWidth: '280px' }}>
          <span style={{
            color: r.error_message ? '#e74c3c' : 'inherit',
            maxWidth: '220px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            display: 'inline-block'
          }}>
            {r.error_message || '-'}
          </span>
          {r.error_message && (
            <div style={{ marginTop: '0.25rem' }}>
              <button
                className="btn btn-sm btn-warning"
                onClick={() => handleAiDiagnose(r)}
                disabled={aiDiagnosing === r.id}
                style={{ fontSize: '0.7rem', padding: '0.15rem 0.4rem' }}
              >
                {aiDiagnosing === r.id ? '...' : 'AI'}
              </button>
            </div>
          )}
          {aiDiagnosis[r.id] && (
            <div style={{ marginTop: '0.25rem', padding: '0.4rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f', fontSize: '0.75rem' }}>
              {aiDiagnosis[r.id].error ? (
                <span style={{ color: '#e74c3c' }}>{aiDiagnosis[r.id].error}</span>
              ) : (
                <>
                  {aiDiagnosis[r.id].explanation && <div>{aiDiagnosis[r.id].explanation}</div>}
                  {aiDiagnosis[r.id].suggested_fix && <div><strong>Fix:</strong> {aiDiagnosis[r.id].suggested_fix}</div>}
                </>
              )}
            </div>
          )}
        </div>
      ),
      csv: r => r.error_message || ''
    }
  ], [])

  const actions = (run: Run) => (
    <div style={{ display: 'flex', gap: '0.35rem' }}>
      <Link to={`/runs/${run.id}`} className="btn btn-sm btn-primary">View</Link>
      {run.workflow_id != null && (
        <Link to={`/workflows/${run.workflow_id}/design`} className="btn btn-sm btn-secondary">Edit</Link>
      )}
      {ACTIVE_STATUSES.includes(run.status) && run.workflow_id != null && (
        <button
          className="btn btn-sm btn-danger"
          onClick={() => cancelMutation.mutate(run)}
          disabled={cancelMutation.isPending}
        >
          Cancel
        </button>
      )}
    </div>
  )

  if (isLoading) {
    return <div className="loading">Loading runs...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>Workflow Runs</h2>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            className="form-select"
            style={{ width: 'auto' }}
            value={workflowFilter}
            onChange={(e) => setWorkflowFilter(e.target.value)}
          >
            <option value="">All workflows</option>
            {workflows.map(w => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
          <button
            className={`btn btn-sm ${tab === 'active' ? 'btn-info' : 'btn-secondary'}`}
            onClick={() => setTab('active')}
          >
            Active
          </button>
          <button
            className={`btn btn-sm ${tab === 'completed' ? 'btn-success' : 'btn-secondary'}`}
            onClick={() => setTab('completed')}
          >
            Completed
          </button>
          <button
            className={`btn btn-sm ${tab === 'all' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab('all')}
          >
            All
          </button>
        </div>
      </div>

      <div className="card">
        <RunsTable
          rows={filtered}
          columns={columns}
          storageKey="admin-runs"
          actions={actions}
          emptyMessage="No runs found in this view"
        />
      </div>
    </div>
  )
}
