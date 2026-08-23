import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { taskApi } from '../services/api'
import { TaskDashboard, TaskColumnDef } from '../components/TaskDashboard'
import { useAuth } from '../components/Auth'

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
  priority?: number | null
  ola_pickup_met?: boolean | null
  ola_closure_met?: boolean | null
  sla_response_met?: boolean | null
  sla_resolution_met?: boolean | null
}

type Tab = 'active' | 'open' | 'review' | 'owned' | 'completed' | 'closed' | 'all'

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

interface RoleTaskDashboardProps {
  role: 'developer' | 'staff' | 'user'
  title: string
}

export const RoleTaskDashboard: React.FC<RoleTaskDashboardProps> = ({ role, title }) => {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('active')
  const queryClient = useQueryClient()

  const { data: tasks, isLoading, error: taskError } = useQuery({
    queryKey: ['role-tasks', role],
    queryFn: async () => {
      const response = await taskApi.listTasks()
      return ((response.data as any).tasks || []) as Task[]
    }
  })

  const takeMutation = useMutation({
    mutationFn: (taskId: number) => taskApi.takeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['role-tasks', role] })
  })

  const completeMutation = useMutation({
    mutationFn: (taskId: number) => taskApi.completeTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['role-tasks', role] })
  })

  const filtered = useMemo(() => {
    if (!tasks) return []

    // Filter by tab status
    let list = tab === 'all' ? tasks : tab === 'active' ? tasks.filter(t => ['open', 'review', 'owned'].includes(t.status)) : tasks.filter(t => t.status === tab)
    
    // Role-based filtering
    if (role === 'user') {
      // Users see only their own tasks
      list = list.filter(t => t.assigned_to_user_id === user?.id)
    } else if (role === 'developer' || role === 'staff') {
      // Developers/Staff see their own + group tasks, but hide closed by default
      const userGroupIds = user?.groups?.map((g: any) => g.id) || []
      list = list.filter(t => 
        t.assigned_to_user_id === user?.id || 
        (t.assigned_group_id && userGroupIds.includes(t.assigned_group_id))
      )
      // Hide closed tasks by default for developer/staff
      if (tab === 'all') {
        list = list.filter(t => t.status !== 'closed')
      }
    }
    
    return list
  }, [tasks, tab, role, user])

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
      key: 'form',
      label: 'Form',
      render: r => r.form_id ? <span className="badge badge-info">Form</span> : '-',
      csv: r => r.form_id ? 'Yes' : 'No'
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
      key: 'priority',
      label: 'Priority',
      render: r => r.priority !== null && r.priority !== undefined
        ? <span className="badge" style={{ backgroundColor: ['#dc3545', '#fd7e14', '#ffc107', '#28a745'][r.priority - 1] || '#6c757d', color: r.priority <= 2 ? 'white' : 'inherit' }}>
            P{r.priority}
          </span>
        : '-',
      csv: r => r.priority ? `P${r.priority}` : ''
    },
    {
      key: 'ola_pickup',
      label: 'OLA Pickup',
      render: r => {
        if (r.ola_pickup_met === null || r.ola_pickup_met === undefined) return <span className="badge badge-warning">Pending</span>
        return r.ola_pickup_met
          ? <span className="badge badge-success">Met</span>
          : <span className="badge badge-danger">Breached</span>
      },
      csv: r => r.ola_pickup_met === null ? 'Pending' : r.ola_pickup_met ? 'Met' : 'Breached'
    },
    {
      key: 'ola_closure',
      label: 'OLA Closure',
      render: r => {
        if (r.ola_closure_met === null || r.ola_closure_met === undefined) return <span className="badge badge-warning">Pending</span>
        return r.ola_closure_met
          ? <span className="badge badge-success">Met</span>
          : <span className="badge badge-danger">Breached</span>
      },
      csv: r => r.ola_closure_met === null ? 'Pending' : r.ola_closure_met ? 'Met' : 'Breached'
    },
    {
      key: 'sla_response',
      label: 'SLA Response',
      render: r => {
        if (r.sla_response_met === null || r.sla_response_met === undefined) return <span className="badge badge-warning">Pending</span>
        return r.sla_response_met
          ? <span className="badge badge-success">Met</span>
          : <span className="badge badge-danger">Breached</span>
      },
      csv: r => r.sla_response_met === null ? 'Pending' : r.sla_response_met ? 'Met' : 'Breached'
    },
    {
      key: 'sla_resolution',
      label: 'SLA Resolution',
      render: r => {
        if (r.sla_resolution_met === null || r.sla_resolution_met === undefined) return <span className="badge badge-warning">Pending</span>
        return r.sla_resolution_met
          ? <span className="badge badge-success">Met</span>
          : <span className="badge badge-danger">Breached</span>
      },
      csv: r => r.sla_resolution_met === null ? 'Pending' : r.sla_resolution_met ? 'Met' : 'Breached'
    }
  ], [])

  const actions = (task: Task) => (
    <div style={{ display: 'flex', gap: '0.35rem' }}>
      <Link to={`/tasks/${task.id}`} className="btn btn-sm btn-secondary">View</Link>
      {task.status === 'open' && role !== 'user' && (
        <button
          className="btn btn-sm btn-info"
          onClick={() => takeMutation.mutate(task.id)}
          disabled={takeMutation.isPending}
        >
          Take
        </button>
      )}
      {task.status === 'owned' && !task.form_id && (
        <button
          className="btn btn-sm btn-success"
          onClick={() => completeMutation.mutate(task.id)}
          disabled={completeMutation.isPending}
        >
          Complete
        </button>
      )}
    </div>
  )

  if (isLoading) {
    return <div className="loading">Loading tasks...</div>
  }

  if (taskError) {
    return <div className="error">Failed to load tasks: {(taskError as Error).message}</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>{title}</h2>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {(['active', 'open', 'review', 'owned', 'completed', 'closed', 'all'] as Tab[]).map(t => (
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
          storageKey={`${role}-tasks`}
          actions={actions}
          emptyMessage={`No ${role} tasks found`}
        />
      </div>
    </div>
  )
}
