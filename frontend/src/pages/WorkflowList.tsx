import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { workflowApi } from '../services/api'

interface Workflow {
  id: number
  name: string
  description: string
  is_active: boolean
  steps_count: number
  runs_count: number
  created_at: string
}

export const WorkflowList: React.FC = () => {
  const [showCreate, setShowCreate] = useState(false)
  const [newWorkflow, setNewWorkflow] = useState({ name: '', description: '' })
  const queryClient = useQueryClient()

  const { data: workflows, isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: async () => {
      const response = await workflowApi.list()
      return response.data
    }
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => 
      workflowApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setShowCreate(false)
      setNewWorkflow({ name: '', description: '' })
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workflowApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    }
  })

  if (isLoading) {
    return <div className="loading">Loading workflows...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>Workflows</h2>
        <button 
          className="btn btn-primary"
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? 'Cancel' : '+ New Workflow'}
        </button>
      </div>

      {showCreate && (
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
            <button type="submit" className="btn btn-success" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Workflow'}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Steps</th>
              <th>Runs</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {workflows?.map((workflow: Workflow) => (
              <tr key={workflow.id}>
                <td>
                  <Link to={`/workflows/${workflow.id}`} style={{ fontWeight: 600 }}>
                    {workflow.name}
                  </Link>
                </td>
                <td>{workflow.description}</td>
                <td>{workflow.steps_count}</td>
                <td>{workflow.runs_count}</td>
                <td>
                  <span className={`badge ${workflow.is_active ? 'badge-success' : 'badge-danger'}`}>
                    {workflow.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>{new Date(workflow.created_at).toLocaleDateString()}</td>
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
