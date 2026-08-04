import React, { useState } from 'react'
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

export const WorkflowList: React.FC = () => {
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const [showCreate, setShowCreate] = useState(false)
  const [newWorkflow, setNewWorkflow] = useState({ name: '', description: '' })
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const queryClient = useQueryClient()

  const { data: workflows, isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: async () => {
      const response = await workflowApi.list()
      return response.data
    }
  })

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
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create workflow')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workflowApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete workflow')
    }
  })

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
          <button 
            className="btn btn-primary"
            onClick={() => setShowCreate(!showCreate)}
          >
            {showCreate ? 'Cancel' : '+ New Workflow'}
          </button>
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

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
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
                      onClick={() => deleteMutation.mutate(workflow.id)}
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
    </div>
  )
}
