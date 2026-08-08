import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { taskApi } from '../services/api'
import { TaskDashboard, TaskColumnDef } from '../components/TaskDashboard'

interface Task {
  id: number
  workflow_run_id: number | null
  step_id: number | null
  title: string
  description: string
  status: string
  assigned_to_user_id: number | null
  assigned_group_id: number | null
  form_id: number | null
  task_data: any
  result_data: any
  created_at: string
  updated_at: string
  completed_at: string | null
  closed_at: string | null
  assigned_user: { id: number; username: string; full_name: string } | null
  assigned_group: { id: number; name: string } | null
}

type Tab = 'open' | 'review' | 'owned' | 'completed' | 'closed' | 'all'

const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case 'open': return 'badge-warning'
    case 'review': return 'badge-info'
    case 'owned': return 'badge-primary'
    case 'completed': return 'badge-success'
    case 'closed': return 'badge-secondary'
    default: return 'badge-secondary'
  }
}

export const AdminTaskDashboard: React.FC = () => {
  const [tab, setTab] = useState<Tab>('all')
  const queryClient = useQueryClient()

  const { data: tasks, isLoading } = useQuery({
    queryKey: ['admin-tasks'],
    queryFn: async () => {
      const response = await taskApi.listTasks()
      return ((response.data as any).tasks || []) as Task[]
    }
  })

  const completeMutation = useMutation({
    mutationFn: (taskId: number) => taskApi.completeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-tasks'] })
  })

  const closeMutation = useMutation({
    mutationFn: (taskId: number) => taskApi.closeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-tasks'] })
  })

  const filtered = useMemo(() => {
    if (!tasks) return []
    if (tab === 'all') return tasks
    return tasks.filter(t => t.status === tab)
  }, [tasks, tab])

  const columns: TaskColumnDef[] = useMemo(() => [
    {
      key: 'id',
      label: 'ID',
      csv: r => String(r.id)
    },
    {
      key: 'title',
      label: 'Title',
      render: r => <Link to={`/tasks/${r.id}`}>{r.title}</Link>,
      csv: r => r.title
    },
    {
      key: 'status',
      label: 'Status',
      render: r => <span className={`badge ${getStatusBadgeClass(r.status)}`}>{r.status}</span>,
      csv: r => r.status
    },
    {
      key: 'assigned_user',
      label: 'Assigned To',
      render: r => r.assigned_user?.full_name || r.assigned_user?.username || '-',
      csv: r => r.assigned_user?.full_name || r.assigned_user?.username || ''
    },
    {
      key: 'assigned_group',
      label: 'Group',
      render: r => r.assigned_group?.name || '-',
      csv: r => r.assigned_group?.name || ''
    },
    {
      key: 'workflow_run_id',
      label: 'Workflow Run',
      render: r => r.workflow_run_id ? <Link to={`/runs/${r.workflow_run_id}`}>#{r.workflow_run_id}</Link> : '-',
      csv: r => r.workflow_run_id ? `#${r.workflow_run_id}` : ''
    },
    {
      key: 'created_at',
      label: 'Created',
      render: r => new Date(r.created_at).toLocaleString(),
      csv: r => r.created_at || ''
    },
    {
      key: 'completed_at',
      label: 'Completed',
      render: r => r.completed_at ? new Date(r.completed_at).toLocaleString() : '-',
      csv: r => r.completed_at || ''
    }
  ], [])

  const actions = (task: Task) => (
    <div style={{ display: 'flex', gap: '0.35rem' }}>
      <Link to={`/tasks/${task.id}`} className="btn btn-sm btn-secondary">View</Link>
      {task.status === 'open' && (
        <button
          className="btn btn-sm btn-info"
          onClick={() => completeMutation.mutate(task.id)}
          disabled={completeMutation.isPending}
        >
          Complete
        </button>
      )}
      {task.status === 'completed' && (
        <button
          className="btn btn-sm btn-success"
          onClick={() => closeMutation.mutate(task.id)}
          disabled={closeMutation.isPending}
        >
          Close
        </button>
      )}
    </div>
  )

  if (isLoading) {
    return <div className="loading">Loading tasks...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>Admin Task Dashboard</h2>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {(['all', 'open', 'review', 'owned', 'completed', 'closed'] as Tab[]).map(t => (
            <button
              key={t}
              className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <TaskDashboard
          rows={filtered}
          columns={columns}
          storageKey="admin-tasks"
          actions={actions}
          emptyMessage="No tasks found"
        />
      </div>
    </div>
  )
}
