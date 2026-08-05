import React, { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { portalApi } from '../services/api'
import { getStatusBadgeClass, formatDuration } from './WorkflowRunsAdmin'

interface PortalWorkflow {
  id: number
  name: string
  description: string
  environment: string
  is_published: boolean
  portal_icon: string
  portal_order: number
  portal_visible: boolean
  entry_form_id?: number | null  // P3.3
}

interface PortalRun {
  id: number
  workflow_id: number
  status: string
  started_at: string
  completed_at: string
  created_at: string
}

interface PortalTask {
  id: number
  title: string
  description: string
  status: string
  workflow_run_id: number | null
  step_id: number | null
  created_at: string
  completed_at: string | null
}

interface PortalBanner {
  enabled: boolean
  title: string
  message: string
  color: string
}

export const Portal: React.FC = () => {
  const [workflows, setWorkflows] = useState<PortalWorkflow[]>([])
  const [myRuns, setMyRuns] = useState<PortalRun[]>([])
  const [myTasks, setMyTasks] = useState<PortalTask[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState<number | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [entryFormWorkflow, setEntryFormWorkflow] = useState<PortalWorkflow | null>(null)
  const [entryFormData, setEntryFormData] = useState<Record<string, any>>({})
  const [banner, setBanner] = useState<PortalBanner>({ enabled: false, title: '', message: '', color: '#f39c12' })

  const load = useCallback(async () => {
    try {
      const [wfResponse, runsResponse, tasksResponse, bannerResponse] = await Promise.all([
        portalApi.listWorkflows(),
        portalApi.myRuns(),
        portalApi.myTasks(),
        axios.get('/api/portal/banner')
      ])
      setWorkflows(wfResponse.data)
      setMyRuns(runsResponse.data)
      setMyTasks(tasksResponse.data || [])
      if (bannerResponse.data.enabled) {
        setBanner(bannerResponse.data)
      }
    } catch (error) {
      console.error('Failed to load portal data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const runWorkflow = async (wf: PortalWorkflow) => {
    // P3.3: If workflow has an entry form, show it first
    if (wf.entry_form_id) {
      setEntryFormWorkflow(wf)
      setEntryFormData({})
      return
    }
    
    setRunning(wf.id)
    try {
      const response = await portalApi.runWorkflow(wf.id, entryFormData)
      setToast(`Started "${wf.name}" (run #${response.data.run_id})`)
      await load()
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    } finally {
      setRunning(null)
      setEntryFormWorkflow(null)
      setEntryFormData({})
    }
  }

  const submitEntryForm = async () => {
    if (!entryFormWorkflow) return
    setRunning(entryFormWorkflow.id)
    try {
      const response = await portalApi.runWorkflow(entryFormWorkflow.id, entryFormData)
      setToast(`Started "${entryFormWorkflow.name}" (run #${response.data.run_id})`)
      await load()
      setEntryFormWorkflow(null)
      setEntryFormData({})
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    } finally {
      setRunning(null)
    }
  }

  const runMap = useMemo(() => {
    const map = new Map<number, string>()
    workflows.forEach(w => map.set(w.id, w.name))
    return map
  }, [workflows])

  if (loading) {
    return <div className="loading">Loading portal...</div>
  }

  return (
    <div>
      {toast && (
        <div className="toast" style={{
          position: 'fixed',
          top: '1rem',
          right: '1rem',
          zIndex: 100,
          background: '#2c3e50',
          color: 'white',
          padding: '0.75rem 1.25rem',
          borderRadius: '6px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.25)'
        }}>
          {toast}
        </div>
      )}

      {banner.enabled && banner.message && (
        <div style={{
          backgroundColor: banner.color,
          color: '#fff',
          padding: '0.75rem 1rem',
          borderRadius: '6px',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem',
          boxShadow: '0 1px 4px rgba(0,0,0,0.15)'
        }}>
          <span style={{ fontSize: '1.3rem', lineHeight: 1, flexShrink: 0 }}>⚠️</span>
          <div style={{ flex: 1 }}>
            {banner.title && <strong style={{ display: 'block', marginBottom: '0.25rem' }}>{banner.title}</strong>}
            <span style={{ fontSize: '0.9rem', opacity: 0.95 }}>{banner.message}</span>
          </div>
        </div>
      )}

      {/* P3.3: Pending tasks section */}
      {myTasks.length > 0 && (
        <div className="card" style={{ marginBottom: '2rem' }}>
          <div className="card-header">
            <h3 className="card-title">📋 My Pending Tasks ({myTasks.length})</h3>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {myTasks.slice(0, 10).map(task => (
                <tr key={task.id}>
                  <td>
                    <div>
                      <strong>{task.title}</strong>
                      {task.description && <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{task.description}</div>}
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${task.status === 'owned' ? 'badge-info' : 'badge-warning'}`}>
                      {task.status}
                    </span>
                  </td>
                  <td>{new Date(task.created_at).toLocaleDateString()}</td>
                  <td>
                    {task.status === 'open' && (
                      <button
                        className="btn btn-sm btn-primary"
                        onClick={() => window.location.href = `/tasks/${task.id}`}
                      >
                        Take Task
                      </button>
                    )}
                    {task.status === 'owned' && (
                      <button
                        className="btn btn-sm btn-success"
                        onClick={() => window.location.href = `/tasks/${task.id}/complete`}
                      >
                        Complete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Entry form modal */}
      {entryFormWorkflow && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => { setEntryFormWorkflow(null); setEntryFormData({}) }}>
          <div className="card" style={{ maxWidth: '500px', width: '90%' }} onClick={e => e.stopPropagation()}>
            <h3>Entry Form: {entryFormWorkflow.name}</h3>
            <p>{entryFormWorkflow.description}</p>
            <div className="form-group">
              <label className="form-label">Sample Field (replace with actual form fields)</label>
              <input
                className="form-input"
                type="text"
                value={entryFormData.sample || ''}
                onChange={e => setEntryFormData({ ...entryFormData, sample: e.target.value })}
                placeholder="Enter data..."
              />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button className="btn btn-primary" onClick={submitEntryForm}>Submit</button>
              <button className="btn btn-secondary" onClick={() => { setEntryFormWorkflow(null); setEntryFormData({}) }}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {workflows.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', opacity: 0.7 }}>
          No workflows are currently available. Check back soon.
        </div>
      ) : (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
          maxWidth: '1400px'
        }}>
          {workflows.map(wf => (
            <div
              key={wf.id}
              className="stat-card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: '0.6rem',
                minHeight: '150px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
                <span style={{ fontSize: '2.2rem', lineHeight: 1 }}>{wf.portal_icon || '⚙️'}</span>
                <h3 className="card-title" style={{ margin: 0, flex: 1 }}>{wf.name}</h3>
              </div>
              <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9rem', flex: 1 }}>
                {wf.description || 'No description provided'}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%' }}>
                <button
                  className="btn btn-sm btn-primary"
                  style={{ marginLeft: 'auto' }}
                  onClick={() => runWorkflow(wf)}
                  disabled={running !== null}
                >
                  {running === wf.id ? 'Submitting...' : 'Submit'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card" style={{ marginTop: '2rem' }}>
        <div className="card-header">
          <h3 className="card-title">My Submissions</h3>
        </div>
        {myRuns.length === 0 ? (
          <p style={{ opacity: 0.6, padding: '1rem' }}>You haven't started any workflows yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Workflow</th>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {myRuns.slice(0, 10).map(run => (
                <tr key={run.id}>
                  <td>#{run.id}</td>
                  <td>{runMap.get(run.workflow_id) || `Workflow #${run.workflow_id}`}</td>
                  <td>
                    <span className={`badge ${getStatusBadgeClass(run.status)}`}>{run.status}</span>
                  </td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</td>
                  <td>{formatDuration(run.started_at, run.completed_at)}</td>
                  <td>
                    <Link to={`/runs/${run.id}`} className="btn btn-sm btn-secondary">Details</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
