import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { workflowApi, runApi, authApi, workflowExportApi } from '../services/api'
import { useAuth } from '../components/Auth'

interface Workflow {
  id: number
  name: string
  description: string
  version: number
  is_active: boolean
  is_published: boolean
  environment: string
  portal_icon: string
  portal_order: number
  portal_visible: boolean
  steps: any[]
  allowed_groups: Array<{id: number, name: string}>
}

interface Run {
  id: number
  status: string
  triggered_by: string
  started_at: string
  completed_at: string
  error_message: string
}

interface Group {
  id: number
  name: string
  is_active: boolean
}

export const WorkflowDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const queryClient = useQueryClient()
  const workflowId = parseInt(id!)
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [permsInitialized, setPermsInitialized] = useState(false)
  const [permsError, setPermsError] = useState('')
  const [portalSettings, setPortalSettings] = useState({ icon: '', order: 0, visible: true })
  const [editMode, setEditMode] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [versionIncremented, setVersionIncremented] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      const response = await workflowApi.get(workflowId)
      return response.data
    },
    enabled: !!id
  })

  const { data: groups } = useQuery({
    queryKey: ['groups'],
    queryFn: async () => {
      const response = await authApi.listGroups()
      return response.data as Group[]
    },
    enabled: canDevelop
  })

  useEffect(() => {
    if (workflow && !permsInitialized) {
      setSelectedGroupIds((workflow.allowed_groups || []).map((g: {id: number}) => g.id))
      setPermsInitialized(true)
    }
    if (workflow) {
      setPortalSettings({
        icon: workflow.portal_icon || '',
        order: workflow.portal_order || 0,
        visible: workflow.portal_visible !== false
      })
      setEditName(workflow.name || '')
      setEditDescription(workflow.description || '')
    }
  }, [workflow, permsInitialized])

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

  const permissionsMutation = useMutation({
    mutationFn: () => workflowApi.setPermissions(workflowId, selectedGroupIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      setPermsError('')
    },
    onError: (err: any) => {
      setPermsError(err.response?.data?.detail || 'Failed to update permissions')
    }
  })

  const publishMutation = useMutation({
    mutationFn: (publish: boolean) =>
      workflowApi.update(workflowId, { is_published: publish }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    }
  })

  const portalMutation = useMutation({
    mutationFn: () =>
      workflowApi.update(workflowId, {
        portal_icon: portalSettings.icon,
        portal_order: portalSettings.order,
        portal_visible: portalSettings.visible
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    }
  })

  const metadataMutation = useMutation({
    mutationFn: () =>
      workflowApi.update(workflowId, {
        name: editName,
        description: editDescription
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setEditMode(false)
    }
  })

  const versionMutation = useMutation({
    mutationFn: () =>
      workflowApi.update(workflowId, { manual_version_increment: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setVersionIncremented(true)
      setTimeout(() => setVersionIncremented(false), 2000)
    }
  })

  const duplicateMutation = useMutation({
    mutationFn: () => workflowExportApi.duplicate(workflowId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      window.location.href = `/workflows/${data.data.id}`
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Failed to duplicate workflow')
    }
  })

  const handleExport = (format: string) => {
    const token = localStorage.getItem('token')
    fetch(`/api/workflows/${workflowId}/export?fmt=${format}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `workflow-${workflow.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${workflowId}.${format}`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      })
      .catch(err => alert('Export failed: ' + err.message))
  }

  const toggleStepMutation = useMutation({
    mutationFn: ({ stepId, enabled }: { stepId: number; enabled: boolean }) =>
      workflowApi.updateStep(workflowId, stepId, { is_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    }
  })

  const toggleStepEnabled = (stepId: number, enabled: boolean) => {
    toggleStepMutation.mutate({ stepId, enabled })
  }

  if (isLoading) {
    return <div className="loading">Loading workflow...</div>
  }

  if (!workflow) {
    return <div className="error">Workflow not found</div>
  }

  const toggleGroup = (groupId: number) => {
    setSelectedGroupIds(prev =>
      prev.includes(groupId) ? prev.filter(gid => gid !== groupId) : [...prev, groupId]
    )
  }

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            {editMode ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
                <input
                  className="form-input"
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="Workflow name"
                />
                <textarea
                  className="form-textarea"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="Workflow description"
                  rows={3}
                />
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-success btn-sm" onClick={() => metadataMutation.mutate()}>
                    Save Changes
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditMode(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h2>{workflow.name}</h2>
                <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>{workflow.description}</p>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                  <button className="btn btn-sm btn-secondary" onClick={() => setEditMode(true)}>
                    Edit Metadata
                  </button>
                  {canDevelop && (
                    <button
                      className="btn btn-sm btn-warning"
                      onClick={() => versionMutation.mutate()}
                      disabled={versionMutation.isPending || versionIncremented}
                    >
                      {versionIncremented ? 'Version Incremented!' : `v${workflow.version} → Increment`}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
          <div style={{ display: 'flex', gap: '1rem', flexShrink: 0 }}>
            {canDevelop && !editMode && (
              <>
                <Link to={`/workflows/${workflowId}/design`} className="btn btn-primary">
                  Edit Workflow
                </Link>
                <button
                  className={`btn ${workflow.is_published ? 'btn-warning' : 'btn-success'}`}
                  onClick={() => publishMutation.mutate(!workflow.is_published)}
                  disabled={publishMutation.isPending}
                >
                  {publishMutation.isPending ? 'Saving...' : (workflow.is_published ? 'Unpublish' : 'Publish')}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => duplicateMutation.mutate()}
                  disabled={duplicateMutation.isPending}
                  title="Duplicate this workflow"
                >
                  {duplicateMutation.isPending ? 'Copying...' : '⧉ Duplicate'}
                </button>
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <button className="btn btn-secondary" onClick={() => setShowExportMenu(!showExportMenu)} title="Export workflow">↓ Export</button>
                  {showExportMenu && (
                    <div style={{
                      position: 'absolute', top: '100%', right: 0, marginTop: '0.25rem',
                      background: 'white', border: '1px solid #ddd', borderRadius: '4px',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.15)', zIndex: 10, minWidth: '120px'
                    }}>
                      <button className="btn btn-sm btn-secondary" style={{ display: 'block', width: '100%', marginBottom: '0.25rem' }} onClick={() => { handleExport('xml'); setShowExportMenu(false); }}>Export XML</button>
                      <button className="btn btn-sm btn-secondary" style={{ display: 'block', width: '100%' }} onClick={() => { handleExport('json'); setShowExportMenu(false); }}>Export JSON</button>
                    </div>
                  )}
                </div>
              </>
            )}
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
        <div className="stat-card">
          <div className="stat-value">
            <span className={`badge ${workflow.is_published ? 'badge-success' : 'badge-warning'}`}>
              {workflow.is_published ? 'Published' : 'Draft'}
            </span>
          </div>
          <div className="stat-label">Portal Visibility</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {workflow.allowed_groups?.length > 0
              ? workflow.allowed_groups.map((g: {id: number; name: string}) => (
                  <span key={g.id} className="badge badge-info" style={{ marginRight: '0.25rem' }}>{g.name}</span>
                ))
              : <span className="badge badge-warning">Devs/Admins</span>}
          </div>
          <div className="stat-label">Visible To</div>
        </div>
        </div>
      </div>

      {canDevelop && (
        <div className="card">
          <h3 className="card-title">Group Permissions</h3>
          {permsError && <div className="error" style={{ marginBottom: '0.5rem' }}>{permsError}</div>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
            {(groups || []).map(g => (
              <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectedGroupIds.includes(g.id)}
                  onChange={() => toggleGroup(g.id)}
                />
                {g.name}
              </label>
            ))}
            {(!groups || groups.length === 0) && (
              <small style={{ color: '#7f8c8d' }}>No groups available</small>
            )}
          </div>
          <button
            className="btn btn-primary"
            onClick={() => permissionsMutation.mutate()}
            disabled={permissionsMutation.isPending}
          >
            {permissionsMutation.isPending ? 'Saving...' : 'Save Permissions'}
          </button>
        </div>
      )}

      {canDevelop && (
        <div className="card">
          <h3 className="card-title">Portal Settings</h3>
          <p style={{ color: '#7f8c8d', marginBottom: '1rem' }}>
            Controls how this workflow appears on the public submission portal. Workflows must be
            published and active to be listed.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>Icon (emoji or text)</label>
              <input
                type="text"
                className="form-input"
                value={portalSettings.icon}
                onChange={(e) => setPortalSettings(s => ({ ...s, icon: e.target.value }))}
                placeholder="🚀"
                style={{ width: '180px' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>Order</label>
              <input
                type="number"
                className="form-input"
                value={portalSettings.order}
                onChange={(e) => setPortalSettings(s => ({ ...s, order: parseInt(e.target.value) || 0 }))}
                style={{ width: '100px' }}
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={portalSettings.visible}
                onChange={(e) => setPortalSettings(s => ({ ...s, visible: e.target.checked }))}
              />
              Visible on portal
            </label>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => portalMutation.mutate()}
            disabled={portalMutation.isPending}
          >
            {portalMutation.isPending ? 'Saving...' : 'Save Portal Settings'}
          </button>
        </div>
      )}

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
              {workflow.steps.map((step: any) => (
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
                    <span className={`badge ${step.is_enabled ? 'badge-success' : 'badge-danger'}`} style={{ marginRight: '0.5rem' }}>
                      {step.is_enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {canDevelop && (
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => toggleStepEnabled(step.id, !step.is_enabled)}
                        disabled={toggleStepMutation.isPending}
                        title={step.is_enabled ? 'Disable step' : 'Enable step'}
                      >
                        {step.is_enabled ? '⏸' : '▶'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>
            {canDevelop
              ? <>No steps defined. <Link to={`/workflows/${workflowId}/design`}>Design workflow</Link></>
              : 'No steps defined.'}
          </p>
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
