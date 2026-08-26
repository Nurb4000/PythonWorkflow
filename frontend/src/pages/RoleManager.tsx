/**
 * Admin Role Manager — CRUD for custom roles.
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

interface Role {
  id: number
  name: string
  description: string
  permissions: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export const RoleManager: React.FC = () => {
  const queryClient = useQueryClient()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    permissions: [] as string[],
    is_active: true
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/admin/roles/`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as { items: Role[]; total: number }
    }
  })

  const createMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const token = localStorage.getItem('token')
      return await axios.post(`${API_URL}/admin/roles/`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setShowCreateForm(false)
      setFormData({ name: '', description: '', permissions: [], is_active: true })
      setSuccess('Role created successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create role')
      setTimeout(() => setError(''), 5000)
    }
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: typeof formData }) => {
      const token = localStorage.getItem('token')
      return await axios.put(`${API_URL}/admin/roles/${id}`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setEditingRole(null)
      setSuccess('Role updated successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update role')
      setTimeout(() => setError(''), 5000)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const token = localStorage.getItem('token')
      return await axios.delete(`${API_URL}/admin/roles/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setSuccess('Role deleted successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete role')
      setTimeout(() => setError(''), 5000)
    }
  })

  const handleEdit = (role: Role) => {
    setEditingRole(role)
    setFormData({
      name: role.name,
      description: role.description,
      permissions: role.permissions || [],
      is_active: role.is_active
    })
  }

  const handleSave = () => {
    if (editingRole) {
      updateMutation.mutate({ id: editingRole.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const availablePermissions = [
    'cmdb_read', 'cmdb_write',
    'workflows_read', 'workflows_write',
    'forms_read', 'forms_write',
    'users_read', 'users_write',
    'reports_read', 'reports_write',
    'admin'
  ]

  return (
    <div style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>Role Management</h2>
        <button className="btn btn-primary" onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? 'Cancel' : '+ New Role'}
        </button>
      </div>

      {error && (
        <div style={{ padding: '0.75rem', backgroundColor: '#f8d7da', borderRadius: '4px', marginBottom: '1rem', color: '#721c24' }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: '0.75rem', backgroundColor: '#d4edda', borderRadius: '4px', marginBottom: '1rem', color: '#155724' }}>
          {success}
        </div>
      )}

      {/* Create/Edit Form */}
      {(showCreateForm || editingRole) && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3 className="card-title">{editingRole ? 'Edit Role' : 'Create New Role'}</h3>
          </div>
          <div style={{ padding: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Role Name</label>
              <input
                type="text"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                placeholder="e.g., auditor, reviewer"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-textarea"
                value={formData.description}
                onChange={(e) => setFormData({...formData, description: e.target.value})}
                rows={3}
                placeholder="What is this role for?"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Permissions</label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem' }}>
                {availablePermissions.map(perm => (
                  <label key={perm} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <input
                      type="checkbox"
                      checked={(formData.permissions || []).includes(perm)}
                      onChange={(e) => {
                        const perms = e.target.checked
                          ? [...(formData.permissions || []), perm]
                          : (formData.permissions || []).filter(p => p !== perm)
                        setFormData({...formData, permissions: perms})
                      }}
                    />
                    {perm.replace(/_/g, ' ')}
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({...formData, is_active: e.target.checked})}
                />
                Active
              </label>
            </div>

            <button className="btn btn-success" onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
              {editingRole ? 'Update Role' : 'Create Role'}
            </button>
          </div>
        </div>
      )}

      {/* Roles List */}
      {isLoading ? (
        <div className="loading">Loading roles...</div>
      ) : data?.items && data.items.length > 0 ? (
        <div style={{ display: 'grid', gap: '1rem' }}>
          {data.items.map(role => (
            <div key={role.id} className="card" style={{ borderLeft: role.is_active ? '4px solid #28a745' : '4px solid #dc3545' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ margin: '0 0 0.25rem' }}>{role.name}</h4>
                  <p style={{ margin: '0 0 0.5rem', color: '#666', fontSize: '0.9rem' }}>{role.description}</p>
                  {role.permissions && role.permissions.length > 0 && (
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {role.permissions.map(perm => (
                        <span key={perm} className="badge badge-info" style={{ fontSize: '0.75rem' }}>{perm}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-sm btn-secondary" onClick={() => handleEdit(role)}>Edit</button>
                  <button className="btn btn-sm btn-danger" onClick={() => {
                    if (confirm(`Delete role "${role.name}"?`)) {
                      deleteMutation.mutate(role.id)
                    }
                  }}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '2rem', color: '#666' }}>
          No custom roles yet. Create one to get started.
        </div>
      )}
    </div>
  )
}
