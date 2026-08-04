import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sqlViewApi } from '../services/api'

interface SQLView {
  id: number
  name: string
  description: string
  definition_sql: string
  is_active: boolean
  created_by: number
  created_at: string
  updated_at: string
}

export const SQLViewManager: React.FC = () => {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({ name: '', description: '', definition_sql: '' })
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [previewSql, setPreviewSql] = useState('')

  const { data: views, isLoading } = useQuery({
    queryKey: ['sql-views'],
    queryFn: async () => {
      const res = await sqlViewApi.list()
      return res.data as SQLView[]
    }
  })

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) => sqlViewApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sql-views'] })
      resetForm()
      setSuccessMessage('View created successfully')
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create view')
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<typeof formData> }) => sqlViewApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sql-views'] })
      resetForm()
      setSuccessMessage('View updated successfully')
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update view')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => sqlViewApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sql-views'] })
      setSuccessMessage('View deleted successfully')
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete view')
    }
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => sqlViewApi.update(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sql-views'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to toggle view status')
    }
  })

  const resetForm = () => {
    setShowForm(false)
    setEditingId(null)
    setFormData({ name: '', description: '', definition_sql: '' })
    setPreviewSql('')
  }

  const startEdit = (view: SQLView) => {
    setFormData({
      name: view.name,
      description: view.description,
      definition_sql: view.definition_sql
    })
    setEditingId(view.id)
    setShowForm(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!formData.name.trim()) {
      setError('View name is required')
      return
    }
    if (!formData.definition_sql.trim()) {
      setError('SQL definition is required')
      return
    }

    if (editingId) {
      updateMutation.mutate({ id: editingId, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const handlePreview = () => {
    setPreviewSql(formData.definition_sql)
  }

  if (isLoading) return <div className="loading">Loading views...</div>

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {successMessage && <div className="success" style={{ marginBottom: '1rem' }}>{successMessage}</div>}

      <div className="card-header">
        <h2>SQL Views</h2>
        <button className="btn btn-primary" onClick={() => { resetForm(); setShowForm(true); }}>
          + New View
        </button>
      </div>

      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        Create named SQL views to simplify complex queries for report nodes and Data Explorer.
        Views are materialized in the database and can be referenced by name.
      </p>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem', borderTop: '3px solid #3498db' }}>
          <h3 className="card-title">{editingId ? 'Edit View' : 'Create New View'}</h3>
          <form onSubmit={handleSubmit}>
            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">View Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
                  placeholder="e.g., active_users_summary"
                  required
                  style={{ fontFamily: 'monospace' }}
                />
                <small style={{ color: '#7f8c8d' }}>Lowercase letters, numbers, underscores only</small>
              </div>

              <div className="form-group">
                <label className="form-label">Description</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Brief description of what this view does"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">SQL Definition *</label>
              <textarea
                className="form-textarea"
                rows={8}
                value={formData.definition_sql}
                onChange={(e) => setFormData({ ...formData, definition_sql: e.target.value })}
                placeholder="CREATE VIEW active_users_summary AS SELECT u.name, COUNT(t.id) as task_count FROM users u LEFT JOIN tasks t ON u.id = t.assigned_to_user_id WHERE u.is_active = true GROUP BY u.name"
                required
                style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
              />
              <small style={{ color: '#7f8c8d' }}>
                Must be a CREATE VIEW statement. Only SELECT queries are allowed inside the view definition.
              </small>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button type="submit" className="btn btn-success" disabled={createMutation.isPending || updateMutation.isPending}>
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : (editingId ? 'Update View' : 'Create View')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handlePreview} disabled={!formData.definition_sql.trim()}>
                Preview SQL
              </button>
              <button type="button" className="btn btn-secondary" onClick={resetForm}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {previewSql && (
        <div className="card" style={{ marginBottom: '1.5rem', background: '#f8f9fa' }}>
          <h3 className="card-title">SQL Preview</h3>
          <pre style={{ background: '#fff', padding: '1rem', borderRadius: '4px', overflow: 'auto', fontSize: '0.85rem', fontFamily: 'monospace', border: '1px solid #ddd' }}>
            {previewSql}
          </pre>
          <button className="btn btn-sm btn-secondary" style={{ marginTop: '0.5rem' }} onClick={() => setPreviewSql('')}>Close Preview</button>
        </div>
      )}

      <div className="card">
        <h3 className="card-title">Views ({views?.length || 0})</h3>
        {(views?.length || 0) === 0 ? (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No SQL views defined yet. Click "+ New View" to create one.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {views?.map((view: SQLView) => (
                <tr key={view.id}>
                  <td><code style={{ background: '#f0f0f0', padding: '0.2rem 0.4rem', borderRadius: '3px' }}>{view.name}</code></td>
                  <td>{view.description || '-'}</td>
                  <td>
                    <span className={`badge ${view.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {view.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{view.created_at ? new Date(view.created_at).toLocaleDateString() : '-'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn btn-sm btn-primary" style={{ marginRight: '0.3rem' }} onClick={() => startEdit(view)}>
                      Edit
                    </button>
                    <button
                      className={`btn btn-sm ${view.is_active ? 'btn-warning' : 'btn-success'}`}
                      style={{ marginRight: '0.3rem' }}
                      onClick={() => toggleActiveMutation.mutate({ id: view.id, is_active: !view.is_active })}
                    >
                      {view.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => {
                        if (confirm(`Delete view "${view.name}"? This will drop it from the database.`)) {
                          deleteMutation.mutate(view.id)
                        }
                      }}
                    >
                      Delete
                    </button>
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
