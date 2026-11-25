import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../services/api'

interface Schedule {
  id: number
  workflow_id: number
  cron_expression: string
  is_enabled: boolean
  last_run_at: string
  next_run_at: string
}

export const ScheduleManager: React.FC = () => {
  const [showAdd, setShowAdd] = useState(false)
  const [newSchedule, setNewSchedule] = useState({
    workflow_id: '',
    cron_expression: '0 0 * * *',
    is_enabled: true
  })
  const queryClient = useQueryClient()

  const { data: schedules, isLoading } = useQuery({
    queryKey: ['schedules'],
    queryFn: async () => {
      const response = await adminApi.listSchedules()
      return response.data
    }
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => adminApi.createSchedule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      setShowAdd(false)
      setNewSchedule({ workflow_id: '', cron_expression: '0 0 * * *', is_enabled: true })
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => 
      adminApi.updateSchedule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminApi.deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
    }
  })

  const handleToggle = async (schedule: Schedule) => {
    await updateMutation.mutateAsync({
      id: schedule.id,
      data: { is_enabled: !schedule.is_enabled }
    })
  }

  if (isLoading) {
    return <div className="loading">Loading schedules...</div>
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <button 
          className="btn btn-primary"
          onClick={() => setShowAdd(!showAdd)}
        >
          {showAdd ? 'Cancel' : '+ New Schedule'}
        </button>
      </div>

      {showAdd && (
        <div className="card">
          <h4 className="card-title">Create Schedule</h4>
          <form onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate({
              ...newSchedule,
              workflow_id: parseInt(newSchedule.workflow_id),
              cron_expression: newSchedule.cron_expression
            })
          }}>
            <div className="form-group">
              <label className="form-label">Workflow ID</label>
              <input
                type="number"
                className="form-input"
                value={newSchedule.workflow_id}
                onChange={(e) => setNewSchedule({...newSchedule, workflow_id: e.target.value})}
                required
                placeholder="Enter workflow ID"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Cron Expression</label>
              <input
                type="text"
                className="form-input"
                value={newSchedule.cron_expression}
                onChange={(e) => setNewSchedule({...newSchedule, cron_expression: e.target.value})}
                required
                placeholder="e.g., 0 0 * * * (daily at midnight)"
              />
              <small style={{ color: '#7f8c8d', display: 'block', marginTop: '0.25rem' }}>
                Format: minute hour day month day_of_week
              </small>
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={newSchedule.is_enabled}
                  onChange={(e) => setNewSchedule({...newSchedule, is_enabled: e.target.checked})}
                />
                Enabled
              </label>
            </div>
            <button type="submit" className="btn btn-success" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Schedule'}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Workflow ID</th>
              <th>Cron Expression</th>
              <th>Status</th>
              <th>Last Run</th>
              <th>Next Run</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules?.map((schedule: Schedule) => (
              <tr key={schedule.id}>
                <td>{schedule.id}</td>
                <td>{schedule.workflow_id}</td>
                <td style={{ fontFamily: 'monospace' }}>{schedule.cron_expression}</td>
                <td>
                  <span className={`badge ${schedule.is_enabled ? 'badge-success' : 'badge-danger'}`}>
                    {schedule.is_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </td>
                <td>{schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : 'Never'}</td>
                <td>{schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : '-'}</td>
                <td>
                  <button 
                    className="btn btn-sm btn-secondary"
                    onClick={() => handleToggle(schedule)}
                    style={{marginRight: '0.5rem'}}
                  >
                    {schedule.is_enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button 
                    className="btn btn-sm btn-danger"
                    onClick={() => deleteMutation.mutate(schedule.id)}
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
