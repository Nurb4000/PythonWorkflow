import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { workflowApi, authApi } from '../services/api'
import { useAuth } from '../components/Auth'

interface Workflow {
  id: number
  name: string
  description: string
  is_active: boolean
  is_published: boolean
  portal_icon: string
  portal_order: number
  steps_count: number
  runs_count: number
  created_at: string
  allowed_groups: Array<{id: number, name: string}>
}

interface Group {
  id: number
  name: string
  is_active: boolean
}

interface AssociatedForm {
  id: number
  name: string
  description: string
}

export const WorkflowList: React.FC = () => {
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const [showCreate, setShowCreate] = useState(false)
  const [newWorkflow, setNewWorkflow] = useState({ name: '', description: '' })
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [deleteConfirm, setDeleteConfirm] = useState<{ workflowId: number; workflowName: string; forms: AssociatedForm[] } | null>(null)
  const [deleteForms, setDeleteForms] = useState(false)
  const queryClient = useQueryClient()

  // Search, filter, sort state
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('name')
  const [sortOrder, setSortOrder] = useState<string>('asc')
  const searchInputRef = useRef<HTMLInputElement>(null)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounce search input -> search term
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setSearchTerm(searchInput), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchInput])

  const { data: workflows, isLoading, isFetching } = useQuery({
    queryKey: ['workflows', searchTerm, statusFilter, sortBy, sortOrder],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (searchTerm) params.search = searchTerm
      if (statusFilter) params.status = statusFilter
      if (sortBy) params.sort_by = sortBy
      if (sortOrder) params.sort_order = sortOrder
      const response = await workflowApi.list(params)
      return response.data
    },
    placeholderData: (previousData) => previousData,
    refetchOnWindowFocus: false,
  })

  // Restore focus to search input after query refetch
  useEffect(() => {
    if (!isFetching && searchInputRef.current && document.activeElement !== searchInputRef.current) {
      // Only restore if we were recently typing (searchInput is non-empty and matches active content)
      if (searchInput && document.activeElement?.tagName !== 'INPUT') {
        searchInputRef.current.focus()
      }
    }
  }, [isFetching, workflows])

  const { data: groups } = useQuery({
    queryKey: ['groups'],
    queryFn: async () => {
      const response = await authApi.listGroups()
      return response.data as Group[]
    },
    enabled: canDevelop
  })

  const [error, setError] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => 
      workflowApi.create({ ...data, allowed_group_ids: selectedGroupIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setShowCreate(false)
      setNewWorkflow({ name: '', description: '' })
      setSelectedGroupIds([])
      setSearchInput('')
      setSearchTerm('')
      setStatusFilter('')
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create workflow')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: async (payload: { id: number; deleteForms: boolean }) => {
      return workflowApi.delete(payload.id, payload.deleteForms)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setDeleteConfirm(null)
      setDeleteForms(false)
      setSearchInput('')
      setSearchTerm('')
      setStatusFilter('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete workflow')
    }
  })

  const handleDeleteClick = async (workflowId: number, workflowName: string) => {
    try {
      const res = await workflowApi.getAssociatedForms(workflowId)
      const forms = res.data.forms || []
      if (forms.length > 0) {
        setDeleteConfirm({ workflowId, workflowName, forms })
        setDeleteForms(false)
      } else {
        deleteMutation.mutate({ id: workflowId, deleteForms: false })
      }
    } catch {
      deleteMutation.mutate({ id: workflowId, deleteForms: false })
    }
  }

  if (isLoading) {
    return <div className="loading">Loading workflows...</div>
  }

  const toggleGroup = (groupId: number) => {
    setSelectedGroupIds(prev =>
      prev.includes(groupId) ? prev.filter(id => id !== groupId) : [...prev, groupId]
    )
  }

  return (
    <div>
      <div className="card-header">
        <h2>Workflows</h2>
        {canDevelop && (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Link to="/workflows/import" className="btn btn-secondary">Import</Link>
            <Link to="/marketplace" className="btn btn-secondary">Marketplace</Link>
            <button 
              className="btn btn-primary"
              onClick={() => setShowCreate(!showCreate)}
            >
              {showCreate ? 'Cancel' : '+ New Workflow'}
            </button>
          </div>
        )}
      </div>

      {canDevelop && showCreate && (
        <div className="card">
          <h3 className="card-title">Create New Workflow</h3>
          <form onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate(newWorkflow)
          }}>
            <div className="form-group">
              <label className="form-label">Name</label>
              <input
                type="text"
                className="form-input"
                value={newWorkflow.name}
                onChange={(e) => setNewWorkflow({...newWorkflow, name: e.target.value})}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-textarea"
                value={newWorkflow.description}
                onChange={(e) => setNewWorkflow({...newWorkflow, description: e.target.value})}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Visible to Groups (empty = developers/admins only)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
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
            </div>
            <button type="submit" className="btn btn-success" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Workflow'}
            </button>
          </form>
        </div>
      )}

      {/* Search, Filter, Sort controls */}
      <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Search</label>
            <input
              ref={searchInputRef}
              type="text"
              className="form-input"
              placeholder="Filter by name or description..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ minWidth: '150px' }}
            >
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="published">Published</option>
              <option value="draft">Draft</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Sort By</label>
            <select
              className="form-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{ minWidth: '150px' }}
            >
              <option value="name">Name</option>
              <option value="created_at">Created Date</option>
              <option value="runs_count">Run Count</option>
              <option value="steps_count">Step Count</option>
              <option value="portal_order">Portal Order</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Direction</label>
            <select
              className="form-select"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              style={{ minWidth: '120px' }}
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </div>
          {(searchInput || statusFilter) && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSearchInput(''); setSearchTerm(''); setStatusFilter('') }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Description</th>
              <th>Steps</th>
              <th>Runs</th>
              <th>Portal Order</th>
              <th>Visible To</th>
              <th>Status</th>
              <th>Published</th>
              <th>Created</th>
              {canDevelop && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {workflows?.map((workflow: Workflow) => (
              <tr key={workflow.id}>
                <td style={{ color: '#7f8c8d', fontSize: '0.85rem' }}>#{workflow.id}</td>
                <td>
                  <Link to={`/workflows/${workflow.id}`} style={{ fontWeight: 600 }}>
                    {workflow.portal_icon ? `${workflow.portal_icon} ` : ''}{workflow.name}
                  </Link>
                </td>
                <td>{workflow.description}</td>
                <td>{workflow.steps_count}</td>
                <td>{workflow.runs_count}</td>
                <td style={{ textAlign: 'center' }}>{workflow.portal_order || 0}</td>
                <td>
                  {workflow.allowed_groups.length > 0 ? workflow.allowed_groups.map(g => (
                    <span key={g.id} className="badge badge-info" style={{ marginRight: '0.25rem' }}>{g.name}</span>
                  )) : (
                    <span className="badge badge-warning">Devs/Admins</span>
                  )}
                </td>
                <td>
                  <span className={`badge ${workflow.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {workflow.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  <span className={`badge ${workflow.is_published ? 'badge-success' : 'badge-warning'}`}>
                    {workflow.is_published ? 'Published' : 'Draft'}
                  </span>
                </td>
                <td>{new Date(workflow.created_at).toLocaleDateString()}</td>
                {canDevelop && (
                  <td>
                    <Link to={`/workflows/${workflow.id}/design`} className="btn btn-sm btn-primary" style={{marginRight: '0.5rem'}}>
                      Design
                    </Link>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleDeleteClick(workflow.id, workflow.name)}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {deleteConfirm && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000
        }} onClick={() => setDeleteConfirm(null)}>
          <div className="card" style={{ maxWidth: '500px', width: '90%', maxHeight: '80vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 className="card-title">Delete Workflow</h3>
            <p>Are you sure you want to delete <strong>{deleteConfirm.workflowName}</strong>?</p>

            {deleteConfirm.forms.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <p style={{ margin: '0 0 0.5rem', color: '#e74c3c' }}>
                  This workflow has {deleteConfirm.forms.length} associated form(s) that will become orphaned:
                </p>
                <ul style={{ marginBottom: '1rem', paddingLeft: '1.5rem' }}>
                  {deleteConfirm.forms.map(f => (
                    <li key={f.id}><strong>{f.name}</strong>{f.description ? ` — ${f.description}` : ''}</li>
                  ))}
                </ul>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={deleteForms}
                    onChange={e => setDeleteForms(e.target.checked)}
                    style={{ width: '18px', height: '18px' }}
                  />
                  <span>Delete these forms as well</span>
                </label>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.5rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setDeleteConfirm(null)}
                disabled={deleteMutation.isPending}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={() => deleteMutation.mutate({ id: deleteConfirm.workflowId, deleteForms })}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete Workflow'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
