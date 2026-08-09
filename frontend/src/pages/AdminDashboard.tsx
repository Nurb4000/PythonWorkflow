import React, { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { adminApi } from '../services/api'
import { ScheduleManager } from '../components/ScheduleManager'

interface Stats {
  total_runs: number
  completed_runs: number
  failed_runs: number
  average_duration_seconds: number
  last_run_at: string
}

interface Run {
  id: number
  workflow_id: number | null
  workflow_name?: string
  status: string
  triggered_by: string
  started_at: string
  completed_at: string
  created_at: string
  error_message: string
}

export const AdminDashboard: React.FC = () => {
  const [days, setDays] = useState(30)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['admin-stats', days],
    queryFn: async () => {
      const response = await adminApi.getStats(undefined, days)
      return response.data as Stats
    }
  })

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ['admin-runs', statusFilter, days],
    queryFn: async () => {
      const response = await adminApi.listRuns({ 
        status: statusFilter || undefined,
        limit: 100
      })
      return response.data as Run[]
    }
  })

  const getStatusBadgeClass = (status: string) => {
    switch(status) {
      case 'completed': return 'badge-success'
      case 'failed': return 'badge-danger'
      case 'running': return 'badge-info'
      default: return 'badge-warning'
    }
  }

  const calculateDuration = (startedAt: string, completedAt: string) => {
    if (!startedAt || !completedAt) return '-'
    const start = new Date(startedAt).getTime()
    const end = new Date(completedAt).getTime()
    const seconds = Math.round((end - start) / 1000)
    
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  if (statsLoading || runsLoading) {
    return <div className="loading">Loading dashboard data...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>Dashboard</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <label>Time Range:</label>
          <select 
            className="form-select" 
            style={{ width: 'auto' }}
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats?.total_runs || 0}</div>
          <div className="stat-label">Total Runs</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#27ae60' }}>{stats?.completed_runs || 0}</div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#e74c3c' }}>{stats?.failed_runs || 0}</div>
          <div className="stat-label">Failed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: '1.5rem' }}>
            {stats?.average_duration_seconds ? `${(stats.average_duration_seconds / 60).toFixed(1)}m` : '-'}
          </div>
          <div className="stat-label">Avg Duration</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: '1rem' }}>
            {stats?.last_run_at ? new Date(stats.last_run_at).toLocaleString() : 'N/A'}
          </div>
          <div className="stat-label">Last Run</div>
        </div>
      </div>

      <ScheduleManager />

      <div className="card" style={{ marginTop: '2rem' }}>
        <div className="card-header">
          <h3 className="card-title">Recent Runs</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button 
              className={`btn btn-sm ${!statusFilter ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setStatusFilter('')}
            >
              All
            </button>
            <button 
              className={`btn btn-sm ${statusFilter === 'completed' ? 'btn-success' : 'btn-secondary'}`}
              onClick={() => setStatusFilter('completed')}
            >
              Completed
            </button>
            <button 
              className={`btn btn-sm ${statusFilter === 'failed' ? 'btn-danger' : 'btn-secondary'}`}
              onClick={() => setStatusFilter('failed')}
            >
              Failed
            </button>
            <button 
              className={`btn btn-sm ${statusFilter === 'running' ? 'btn-info' : 'btn-secondary'}`}
              onClick={() => setStatusFilter('running')}
            >
              Running
            </button>
          </div>
        </div>

        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Workflow</th>
              <th>Status</th>
              <th>Triggered By</th>
              <th>Started</th>
              <th>Completed</th>
              <th>Duration</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {runs?.map((run: Run) => (
              <tr key={run.id}>
                <td>#{run.id}</td>
                <td>{run.workflow_name || (run.workflow_id != null ? `#${run.workflow_id}` : 'Unknown')}</td>
                <td>
                  <span className={`badge ${getStatusBadgeClass(run.status)}`}>
                    {run.status}
                  </span>
                </td>
                <td>{run.triggered_by}</td>
                <td>{run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</td>
                <td>{run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}</td>
                <td>{calculateDuration(run.started_at, run.completed_at)}</td>
                <td style={{ 
                  color: run.error_message ? '#e74c3c' : 'inherit',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}>
                  {run.error_message || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* System Logs */}
      <SystemLogsViewer />
    </div>
  )
}

const SystemLogsViewer: React.FC = () => {
  const [showLogs, setShowLogs] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [lines, setLines] = useState(500)
  const logContainerRef = useRef<HTMLDivElement>(null)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const params: any = { lines }
      if (searchTerm) params.search = searchTerm
      if (levelFilter) params.level = levelFilter
      const res = await adminApi.getLogs(params)
      setLogs(res.data.logs || [])
    } catch {
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (showLogs) fetchLogs()
  }, [showLogs, lines])

  const handleExport = async () => {
    try {
      const params: any = { lines: Math.min(lines * 10, 5000) }
      if (searchTerm) params.search = searchTerm
      if (levelFilter) params.level = levelFilter
      const res = await adminApi.exportLogs(params)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `system-logs-${new Date().toISOString().slice(0, 10)}.txt`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      // Silently fail
    }
  }

  const filteredLogs = logs.filter(line => {
    if (searchTerm && !line.toLowerCase().includes(searchTerm.toLowerCase())) return false
    if (levelFilter && !line.includes(`[${levelFilter.toUpperCase()}]`)) return false
    return true
  })

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <h3 className="card-title">System Logs</h3>
        <button
          className={`btn btn-sm ${showLogs ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShowLogs(!showLogs)}
        >
          {showLogs ? 'Hide Logs' : 'View Logs'}
        </button>
      </div>

      {showLogs && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="text"
              className="form-input"
              placeholder="Search logs..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ maxWidth: '250px' }}
            />
            <select
              className="form-select"
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              style={{ maxWidth: '150px' }}
            >
              <option value="">All Levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
            <select
              className="form-select"
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
              style={{ maxWidth: '120px' }}
            >
              <option value={100}>100 lines</option>
              <option value={500}>500 lines</option>
              <option value={1000}>1000 lines</option>
              <option value={5000}>5000 lines</option>
            </select>
            <button className="btn btn-sm btn-primary" onClick={fetchLogs} disabled={loading}>
              {loading ? 'Loading...' : 'Refresh'}
            </button>
            <button className="btn btn-sm btn-secondary" onClick={handleExport}>
              Export
            </button>
          </div>

          <div
            ref={logContainerRef}
            style={{
              background: '#1a1a2e',
              color: '#e0e0e0',
              fontFamily: 'monospace',
              fontSize: '0.8rem',
              padding: '1rem',
              borderRadius: '4px',
              maxHeight: '500px',
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {filteredLogs.length === 0 && !loading ? (
              <span style={{ color: '#888' }}>No logs found</span>
            ) : (
              filteredLogs.map((line, i) => {
                let color = '#e0e0e0'
                if (line.includes('[ERROR]') || line.includes('[CRITICAL]')) color = '#ff6b6b'
                else if (line.includes('[WARNING]')) color = '#ffd93d'
                else if (line.includes('[INFO]')) color = '#6bcb77'
                else if (line.includes('[DEBUG]')) color = '#888'
                return (
                  <div key={i} style={{ color }}>
                    {line}
                  </div>
                )
              })
            )}
          </div>
        </>
      )}
    </div>
  )
}
