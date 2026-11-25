import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portalApi } from '../services/api'
import { getStatusBadgeClass, formatDuration } from './WorkflowRunsAdmin'

interface MyRun {
  id: number
  workflow_id: number
  workflow_name: string
  status: string
  triggered_by: string
  started_at: string
  completed_at: string
  error_message: string
  created_at: string
}

export const MySubmissions: React.FC = () => {
  const [runs, setRuns] = useState<MyRun[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')

  const load = useCallback(async () => {
    try {
      const res = await portalApi.myRuns()
      setRuns(res.data)
    } catch (error) {
      console.error('Failed to load runs:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filtered = statusFilter
    ? runs.filter(r => r.status === statusFilter)
    : runs

  const statuses = Array.from(new Set(runs.map(r => r.status)))

  if (loading) return <div className="loading">Loading submissions...</div>

  return (
    <div>
      <h2>My Submissions</h2>

      {runs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', opacity: 0.7 }}>
          You haven't started any workflows yet.
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <button
              className={`btn btn-sm ${!statusFilter ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStatusFilter('')}
            >
              All ({runs.length})
            </button>
            {statuses.map(s => (
              <button
                key={s}
                className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setStatusFilter(s)}
              >
                {s} ({runs.filter(r => r.status === s).length})
              </button>
            ))}
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Workflow</th>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(run => (
                <tr key={run.id}>
                  <td>#{run.id}</td>
                  <td>{run.workflow_name || `Workflow #${run.workflow_id}`}</td>
                  <td>
                    <span className={`badge ${getStatusBadgeClass(run.status)}`}>{run.status}</span>
                  </td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</td>
                  <td>{formatDuration(run.started_at, run.completed_at)}</td>
                  <td style={{ maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.error_message ? <span style={{ color: '#e74c3c', fontSize: '0.8rem' }}>{run.error_message}</span> : '-'}
                  </td>
                  <td>
                    <Link to={`/runs/${run.id}`} className="btn btn-sm btn-primary">View</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
