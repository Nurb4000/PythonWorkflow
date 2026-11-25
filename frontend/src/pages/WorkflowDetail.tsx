import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { workflowApi, runApi, authApi, workflowExportApi, marketplaceApi, formsApi, servicesApi } from '../services/api'
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
  show_in_portal: boolean
  entry_form_id: number | null
  service_id: number | null
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
  const navigate = useNavigate()
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const queryClient = useQueryClient()
  const workflowId = parseInt(id!)
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [permsInitialized, setPermsInitialized] = useState(false)
  const [permsError, setPermsError] = useState('')
  const [portalSettings, setPortalSettings] = useState({ icon: '', order: 0, visible: true, showInPortal: true, linkUrl: '' })
  const [editMode, setEditMode] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [versionIncremented, setVersionIncremented] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showPublishModal, setShowPublishModal] = useState(false)
  const [publishForm, setPublishForm] = useState({
    name: '',
    description: '',
    category: 'General',
    tags: '',
    status: 'published',
  })
  const [publishError, setPublishError] = useState('')
  const [publishSuccess, setPublishSuccess] = useState(false)

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

  const { data: forms } = useQuery<Array<{id: number, name: string, description: string}>>({
    queryKey: ['forms-list'],
    queryFn: async () => {
      const response = await formsApi.list()
      const d = response.data as any
      return (d.items || d) as Array<{id: number, name: string, description: string}>
    },
    enabled: canDevelop
  })

  const [entryFormId, setEntryFormId] = useState<number | null>(null)
  const [selectedServiceId, setSelectedServiceId] = useState<number | null>(null)

  const { data: services } = useQuery<Array<{id: number, name: string, key: string, icon: string, is_active: boolean}>>({
    queryKey: ['services-catalog'],
    queryFn: async () => {
      const response = await servicesApi.listServices()
      const d = response.data as any
      return (d.items || d) as Array<{id: number, name: string, key: string, icon: string, is_active: boolean}>
    },
    enabled: canDevelop,
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
        visible: workflow.portal_visible !== false,
        showInPortal: workflow.show_in_portal !== false,
        linkUrl: (workflow.config?.portal_link_url || '')
      })
      setEditName(workflow.name || '')
      setEditDescription(workflow.description || '')
      setEntryFormId(workflow.entry_form_id ?? null)
      setSelectedServiceId(workflow.service_id ?? null)
    }
  }, [workflow, permsInitialized])

  const { data: runs } = useQuery({
    queryKey: ['runs', workflowId],
    queryFn: async () => {
      const response = await runApi.list(workflowId)
      return response.data.runs || []
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

  const isActiveMutation = useMutation({
    mutationFn: (active: boolean) =>
      workflowApi.update(workflowId, { is_active: active }),
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
        portal_visible: portalSettings.visible,
        show_in_portal: portalSettings.showInPortal,
        portal_link_url: portalSettings.linkUrl || undefined,
        entry_form_id: entryFormId,
        service_id: selectedServiceId
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

  const publishToMarketplaceMutation = useMutation({
    mutationFn: async () => {
      setPublishError('')
      setPublishSuccess(false)
      // First, export the workflow as JSON
      const token = localStorage.getItem('token')
      const exportRes = await fetch(`/api/workflows/${workflowId}/export?fmt=json`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!exportRes.ok) {
        const errBody = await exportRes.text()
        throw new Error(`Export failed (${exportRes.status}): ${errBody}`)
      }
      const content = await exportRes.text()

      // Then publish to marketplace
      const tagsArray = publishForm.tags.split(',').map((t: string) => t.trim()).filter(Boolean)
      return marketplaceApi.createItem({
        item_type: 'workflow',
        name: publishForm.name || workflow?.name,
        description: publishForm.description || workflow?.description || '',
        category: publishForm.category,
        tags: tagsArray,
        content,
        content_format: 'json',
        status: publishForm.status,
      })
    },
    onSuccess: () => {
      setPublishSuccess(true)
      queryClient.invalidateQueries({ queryKey: ['marketplace-items'] })
    },
    onError: (err: any) => {
      setPublishError(err.response?.data?.detail || err.message || 'Failed to publish')
    },
  })

  const handleOpenPublishModal = () => {
    setPublishForm({
      name: workflow?.name || '',
      description: workflow?.description || '',
      category: 'General',
      tags: '',
      status: 'published',
    })
    setPublishError('')
    setPublishSuccess(false)
    setShowPublishModal(true)
  }

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
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.85rem', color: '#666' }}>
                  <input
                    type="checkbox"
                    checked={portalSettings.showInPortal}
                    onChange={(e) => {
                      if (!e.target.checked && !selectedServiceId) {
                        if (!confirm('This workflow is not associated with a service. Unchecking will hide it from the Offerings page, making it inaccessible to end users. Continue?')) {
                          return
                        }
                      }
                      setPortalSettings(s => ({ ...s, showInPortal: e.target.checked }))
                    }}
                  />
                  Show on Offerings page
                </label>
                <button
                  className={`btn ${workflow.is_active ? 'btn-warning' : 'btn-success'}`}
                  onClick={() => isActiveMutation.mutate(!workflow.is_active)}
                  disabled={isActiveMutation.isPending}
                  title={workflow.is_active ? 'Deactivate workflow' : 'Activate workflow'}
                >
                  {isActiveMutation.isPending ? '...' : (workflow.is_active ? 'Deactivate' : 'Activate')}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => duplicateMutation.mutate()}
                  disabled={duplicateMutation.isPending}
                  title="Duplicate this workflow"
                >
                  {duplicateMutation.isPending ? 'Copying...' : '⧉ Duplicate'}
                </button>
                <button
                  className="btn btn-info"
                  onClick={handleOpenPublishModal}
                  title="Publish this workflow to the marketplace"
                >
                  ⊕ Publish to Marketplace
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

        {!portalSettings.showInPortal && !selectedServiceId && canDevelop && (
          <div className="error" style={{ marginTop: '1rem' }}>
            Warning: This workflow is hidden from the Offerings page but has no service assigned. It will be inaccessible to end users until associated with a service in the Offerings Settings below.
          </div>
        )}

        {editMode && (
          <div style={{ padding: '0 1rem 1rem' }}>
            <textarea
              className="form-textarea"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="Workflow description"
              rows={3}
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>
        )}

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
          <div className="stat-label">Offerings Visibility</div>
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
          <h3 className="card-title">Offerings Settings</h3>
          <p style={{ color: '#7f8c8d', marginBottom: '1rem' }}>
            Controls how this workflow appears on the Offerings page. Workflows must be
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
          </div>
          <div className="form-group">
            <label className="form-label">External Link URL</label>
            <input
              type="url"
              className="form-input"
              value={portalSettings.linkUrl}
              onChange={(e) => setPortalSettings(s => ({ ...s, linkUrl: e.target.value }))}
              placeholder="https://example.com — replaces 'Submit' with 'Go To' on the Offerings page"
              style={{ maxWidth: '500px' }}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Entry Form (shown before workflow starts)</label>
            <select
              className="form-select"
              value={entryFormId || ''}
              onChange={(e) => setEntryFormId(e.target.value ? Number(e.target.value) : null)}
              style={{ maxWidth: '400px' }}
            >
              <option value="">None (start directly)</option>
              {(forms || []).map(f => (
                <option key={f.id} value={f.id}>{f.name}{f.description ? ` — ${f.description}` : ''}</option>
              ))}
            </select>
            {entryFormId && (
              <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.35rem' }}>
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => navigate(`/forms?preview=${entryFormId}`)}
                  title="Preview this form"
                  style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                >
                  👁 Preview
                </button>
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => navigate(`/forms?editing=1&id=${entryFormId}`)}
                  title="Edit this form"
                  style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                >
                  ✏️ Edit
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => navigate('/forms?editing=1')}
                  title="Create a new form"
                  style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                >
                  + New Form
                </button>
              </div>
            )}
            <small style={{ color: '#7f8c8d' }}>When set, users must fill out this form before the workflow runs. Form data becomes the workflow's input. Saved with "Save Offerings Settings".</small>
          </div>
          <div className="form-group">
            <label className="form-label">Service (organize under a service in the Catalog)</label>
            <select
              className="form-select"
              value={selectedServiceId || ''}
              onChange={(e) => setSelectedServiceId(e.target.value ? Number(e.target.value) : null)}
              style={{ maxWidth: '400px' }}
            >
              <option value="">— Unassigned —</option>
              {(services || []).filter(s => s.is_active).map(s => (
                <option key={s.id} value={s.id}>{s.icon || '📋'} {s.name} ({s.key})</option>
              ))}
            </select>
            <small style={{ color: '#7f8c8d' }}>Associates this workflow with a service so it appears in the Service Catalog. Saved with "Save Offerings Settings".</small>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-primary"
              onClick={() => portalMutation.mutate()}
              disabled={portalMutation.isPending}
            >
              {portalMutation.isPending ? 'Saving...' : 'Save Offerings Settings'}
            </button>
          </div>
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

      {/* Publish to Marketplace Modal */}
      {showPublishModal && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setShowPublishModal(false)}
        >
          <div
            className="card"
            style={{ maxWidth: '550px', width: '90%', maxHeight: '85vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 className="card-title" style={{ margin: 0 }}>Publish to Marketplace</h3>
              <button onClick={() => setShowPublishModal(false)} style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#999' }}>&times;</button>
            </div>

            {publishSuccess && (
              <div style={{ padding: '0.75rem', background: '#f0fff4', borderRadius: '6px', marginBottom: '1rem', color: '#27ae60' }}>
                Workflow published to marketplace successfully!
              </div>
            )}

            {publishError && (
              <div style={{ padding: '0.75rem', background: '#fdf2f2', borderRadius: '6px', marginBottom: '1rem', color: '#e74c3c' }}>
                {publishError}
              </div>
            )}

            {!publishSuccess && (
              <>
                <p style={{ color: '#666', fontSize: '0.9rem', marginBottom: '1rem' }}>
                  This will export the current workflow and publish it to the marketplace so others can discover and install it.
                </p>

                <div className="form-group">
                  <label className="form-label">Name</label>
                  <input
                    className="form-input"
                    type="text"
                    value={publishForm.name}
                    onChange={(e) => setPublishForm({ ...publishForm, name: e.target.value })}
                    placeholder="Marketplace listing name"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    value={publishForm.description}
                    onChange={(e) => setPublishForm({ ...publishForm, description: e.target.value })}
                    placeholder="Describe what this workflow does..."
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Category</label>
                  <select
                    className="form-select"
                    value={publishForm.category}
                    onChange={(e) => setPublishForm({ ...publishForm, category: e.target.value })}
                  >
                    <option value="Data / ETL">Data / ETL</option>
                    <option value="Notifications">Notifications</option>
                    <option value="Approvals & Tasks">Approvals & Tasks</option>
                    <option value="Reporting">Reporting</option>
                    <option value="Integrations">Integrations</option>
                    <option value="Schedules & Maintenance">Schedules & Maintenance</option>
                    <option value="Onboarding">Onboarding</option>
                    <option value="General">General</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Tags (comma-separated)</label>
                  <input
                    className="form-input"
                    type="text"
                    value={publishForm.tags}
                    onChange={(e) => setPublishForm({ ...publishForm, tags: e.target.value })}
                    placeholder="e.g., etl, data, automated"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Status</label>
                  <select
                    className="form-select"
                    value={publishForm.status}
                    onChange={(e) => setPublishForm({ ...publishForm, status: e.target.value })}
                  >
                    <option value="published">Published (visible to all)</option>
                    <option value="draft">Draft (only visible to you)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem' }}>
                  <button
                    className="btn btn-success"
                    onClick={() => publishToMarketplaceMutation.mutate()}
                    disabled={publishToMarketplaceMutation.isPending}
                  >
                    {publishToMarketplaceMutation.isPending ? 'Publishing...' : 'Publish to Marketplace'}
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => setShowPublishModal(false)}
                    disabled={publishToMarketplaceMutation.isPending}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}

            {publishSuccess && (
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                <Link to="/marketplace" className="btn btn-primary">View Marketplace</Link>
                <button className="btn btn-secondary" onClick={() => setShowPublishModal(false)}>Close</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
