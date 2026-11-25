import React, { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { adminApi, cmdbApi, dateTargetsApi, servicesApi } from '../services/api'
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
  const [showSchedules, setShowSchedules] = useState(false)
  const [showRecentRuns, setShowRecentRuns] = useState(false)

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

      <div className="card" style={{ marginTop: '2rem' }}>
        <div className="card-header">
          <h3 className="card-title">Schedules</h3>
          <button
            className={`btn btn-sm ${showSchedules ? 'btn-secondary' : 'btn-primary'}`}
            onClick={() => setShowSchedules(!showSchedules)}
          >
            {showSchedules ? 'Hide Schedules' : 'View Schedules'}
          </button>
        </div>

        {showSchedules && <ScheduleManager />}
      </div>

      <div className="card" style={{ marginTop: '2rem' }}>
        <div className="card-header">
          <h3 className="card-title">Recent Runs</h3>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              className={`btn btn-sm ${showRecentRuns ? 'btn-secondary' : 'btn-primary'}`}
              onClick={() => setShowRecentRuns(!showRecentRuns)}
            >
              {showRecentRuns ? 'Hide Runs' : 'View Runs'}
            </button>
            {showRecentRuns && (
              <>
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
              </>
            )}
          </div>
        </div>

        {showRecentRuns && (
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
                 <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs?.map((run: Run) => (
                  <tr key={run.id}>
                    <td><Link to={`/runs/${run.id}`}>#{run.id}</Link></td>
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
                    <td>
                      <Link to={`/runs/${run.id}`} className="btn btn-sm btn-primary">View</Link>
                    </td>
                  </tr>
                ))}
             </tbody>
          </table>
        )}
      </div>

      {/* System Logs */}
      <SystemLogsViewer />

      {/* CMDB Dashboard */}
      <CMDBDashboardWidget />

      {/* SLA Monitoring Dashboard (Phase 5) */}
      <SLADashboardWidget daysProp={days} />

      {/* OLA Monitoring Dashboard (Task-level) */}
      <OLADashboardWidget daysProp={days} />

      {/* Date Target Monitoring (INCIDENT_CHANGE_PLAN Phase 4.1) */}
      <DateTargetWidget daysProp={days} />

      {/* D4: Data Hygiene Report */}
      <HygieneReportWidget />
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

interface CMDBStats {
  total_types: number
  total_items: number
  items_by_status: Record<string, number>
  items_by_type: Array<{type_id: number; type_name: string; icon: string; count: number}>
  recent_changes: number
}

const CMDBDashboardWidget: React.FC = () => {
  const [showCMDB, setShowCMDB] = useState(false)
  const [days, setDays] = useState(30)

  const { data: stats, isLoading } = useQuery({
    queryKey: ['cmdb-stats', days],
    queryFn: async () => {
      const res = await cmdbApi.getStats(days)
      return res.data as CMDBStats
    },
    enabled: showCMDB,
  })

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <h3 className="card-title">CMDB Overview</h3>
        <button
          className={`btn btn-sm ${showCMDB ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShowCMDB(!showCMDB)}
        >
          {showCMDB ? 'Hide CMDB' : 'View CMDB'}
        </button>
      </div>

      {showCMDB && (
        <>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
            <label>Changes in last:</label>
            <select
              className="form-select"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              style={{ width: 'auto' }}
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>

          {isLoading ? (
            <div className="loading">Loading CMDB stats...</div>
          ) : stats ? (
            <>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{stats.total_types}</div>
                  <div className="stat-label">CI Types</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.total_items}</div>
                  <div className="stat-label">Total Items</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value" style={{ color: '#17a2b8' }}>{stats.recent_changes}</div>
                  <div className="stat-label">Recent Changes</div>
                </div>
              </div>

              {Object.keys(stats.items_by_status).length > 0 && (
                <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
                  <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Items by Status</h4>
                  <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                    {Object.entries(stats.items_by_status).map(([status, count]) => {
                      const colors: Record<string, string> = {
                        active: '#28a745',
                        maintenance: '#ffc107',
                        retired: '#6c757d',
                        decommissioned: '#dc3545',
                      }
                      return (
                        <div key={status} style={{
                          display: 'flex', alignItems: 'center', gap: '0.4rem',
                          padding: '4px 12px', borderRadius: '16px',
                          backgroundColor: (colors[status] || '#6c757d') + '22',
                          border: `1px solid ${colors[status] || '#6c757d'}`,
                        }}>
                          <span style={{ fontWeight: 'bold', color: colors[status] || '#6c757d' }}>{count}</span>
                          <span style={{ fontSize: '0.85rem', textTransform: 'capitalize' }}>{status}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {stats.items_by_type.length > 0 && (
                <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
                  <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Items by Type</h4>
                  <table className="table" style={{ fontSize: '0.85rem' }}>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th style={{ textAlign: 'right' }}>Items</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.items_by_type.map((t) => (
                        <tr key={t.type_id}>
                          <td>{t.icon ? t.icon + ' ' : ''}{t.type_name}</td>
                          <td style={{ textAlign: 'right', fontWeight: 'bold' }}>{t.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

// SLA Monitoring Dashboard Widget (Phase 5)
interface SLAStats {
  total_runs_with_sla: number
  response_met_count: number
  response_breached_count: number
  response_pending_count: number
  resolution_met_count: number
  resolution_breached_count: number
  resolution_pending_count: number
  response_compliance_pct: number
  resolution_compliance_pct: number
  top_breach_services: Array<{ service_id: number; service_name: string; breach_count: number }>
}

const SLADashboardWidget: React.FC<{ daysProp: number }> = ({ daysProp }) => {
  const [showSLA, setShowSLA] = useState(false)

  const { data: slaStats, isLoading } = useQuery({
    queryKey: ['sla-stats', daysProp],
    queryFn: async () => {
      const res = await servicesApi.getSlaStats(daysProp)
      return res.data as SLAStats
    },
    enabled: showSLA,
  })

  const complianceColor = (pct: number) => {
    if (pct >= 90) return '#28a745'
    if (pct >= 70) return '#ffc107'
    return '#dc3545'
  }

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <h3 className="card-title">SLA Monitoring</h3>
        <button
          className={`btn btn-sm ${showSLA ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShowSLA(!showSLA)}
        >
          {showSLA ? 'Hide SLA' : 'View SLA'}
        </button>
      </div>

      {showSLA && (
        <>
          {isLoading ? (
            <div className="loading">Loading SLA stats...</div>
          ) : slaStats ? (
            <>
              {slaStats.total_runs_with_sla === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
                  No SLA-tracked runs in the selected period. Configure SLA targets on services and submit requests with priority to start tracking.
                </div>
              ) : (
                <>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <div className="stat-value">{slaStats.total_runs_with_sla}</div>
                      <div className="stat-label">Runs with SLA</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: complianceColor(slaStats.response_compliance_pct), fontSize: '1.8rem' }}>
                        {slaStats.response_compliance_pct}%
                      </div>
                      <div className="stat-label">Response Compliance</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: complianceColor(slaStats.resolution_compliance_pct), fontSize: '1.8rem' }}>
                        {slaStats.resolution_compliance_pct}%
                      </div>
                      <div className="stat-label">Resolution Compliance</div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                    {/* Response breakdown */}
                    <div className="card" style={{ padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Response SLA</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Met</span>
                          <strong style={{ color: '#28a745' }}>{slaStats.response_met_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Breached</span>
                          <strong style={{ color: '#dc3545' }}>{slaStats.response_breached_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Pending</span>
                          <strong style={{ color: '#ffc107' }}>{slaStats.response_pending_count}</strong>
                        </div>
                      </div>
                    </div>

                    {/* Resolution breakdown */}
                    <div className="card" style={{ padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Resolution SLA</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Met</span>
                          <strong style={{ color: '#28a745' }}>{slaStats.resolution_met_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Breached</span>
                          <strong style={{ color: '#dc3545' }}>{slaStats.resolution_breached_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Pending</span>
                          <strong style={{ color: '#ffc107' }}>{slaStats.resolution_pending_count}</strong>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Top breach services */}
                  {slaStats.top_breach_services.length > 0 && (
                    <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Top Services by Breach Count</h4>
                      <table className="table" style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Service</th>
                            <th style={{ textAlign: 'right' }}>Breaches</th>
                          </tr>
                        </thead>
                        <tbody>
                          {slaStats.top_breach_services.map((s) => (
                            <tr key={s.service_id}>
                              <td>{s.service_name}</td>
                              <td style={{ textAlign: 'right', fontWeight: 'bold', color: '#dc3545' }}>{s.breach_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

// OLA Monitoring Dashboard Widget (Task-level)
interface OLAStats {
  total_tasks_with_ola: number
  pickup_met_count: number
  pickup_breached_count: number
  pickup_pending_count: number
  closure_met_count: number
  closure_breached_count: number
  closure_pending_count: number
  pickup_compliance_pct: number
  closure_compliance_pct: number
  top_breach_groups: Array<{ group_id: number; group_name: string; breach_count: number }>
}

const OLADashboardWidget: React.FC<{ daysProp: number }> = ({ daysProp }) => {
  const [showOLA, setShowOLA] = useState(false)

  const { data: olaStats, isLoading } = useQuery({
    queryKey: ['ola-stats', daysProp],
    queryFn: async () => {
      const res = await servicesApi.getOlaStats(daysProp)
      return res.data as OLAStats
    },
    enabled: showOLA,
  })

  const complianceColor = (pct: number) => {
    if (pct >= 90) return '#28a745'
    if (pct >= 70) return '#ffc107'
    return '#dc3545'
  }

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <h3 className="card-title">OLA Monitoring (Tasks)</h3>
        <button
          className={`btn btn-sm ${showOLA ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShowOLA(!showOLA)}
        >
          {showOLA ? 'Hide OLA' : 'View OLA'}
        </button>
      </div>

      {showOLA && (
        <>
          {isLoading ? (
            <div className="loading">Loading OLA stats...</div>
          ) : olaStats ? (
            <>
              {olaStats.total_tasks_with_ola === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
                  No OLA-tracked tasks in the selected period. Configure OLA targets on groups and assign tasks with priority to start tracking.
                </div>
              ) : (
                <>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <div className="stat-value">{olaStats.total_tasks_with_ola}</div>
                      <div className="stat-label">Tasks with OLA</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: complianceColor(olaStats.pickup_compliance_pct), fontSize: '1.8rem' }}>
                        {olaStats.pickup_compliance_pct}%
                      </div>
                      <div className="stat-label">Pickup Compliance</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: complianceColor(olaStats.closure_compliance_pct), fontSize: '1.8rem' }}>
                        {olaStats.closure_compliance_pct}%
                      </div>
                      <div className="stat-label">Closure Compliance</div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                    <div className="card" style={{ padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Pickup OLA</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Met</span>
                          <strong style={{ color: '#28a745' }}>{olaStats.pickup_met_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Breached</span>
                          <strong style={{ color: '#dc3545' }}>{olaStats.pickup_breached_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Pending</span>
                          <strong style={{ color: '#ffc107' }}>{olaStats.pickup_pending_count}</strong>
                        </div>
                      </div>
                    </div>

                    <div className="card" style={{ padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Closure OLA</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Met</span>
                          <strong style={{ color: '#28a745' }}>{olaStats.closure_met_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Breached</span>
                          <strong style={{ color: '#dc3545' }}>{olaStats.closure_breached_count}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Pending</span>
                          <strong style={{ color: '#ffc107' }}>{olaStats.closure_pending_count}</strong>
                        </div>
                      </div>
                    </div>
                  </div>

                  {olaStats.top_breach_groups.length > 0 && (
                    <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Top Groups by Breach Count</h4>
                      <table className="table" style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Group</th>
                            <th style={{ textAlign: 'right' }}>Breaches</th>
                          </tr>
                        </thead>
                        <tbody>
                          {olaStats.top_breach_groups.map((g) => (
                            <tr key={g.group_id}>
                              <td>{g.group_name}</td>
                              <td style={{ textAlign: 'right', fontWeight: 'bold', color: '#dc3545' }}>{g.breach_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

// Date Target Monitoring Widget (INCIDENT_CHANGE_PLAN Phase 4.1)
interface DateTargetStats {
  total: number
  met: number
  breached: number
  pending: number
  compliance_pct: number | null
  period_days: number
}

interface DateTarget {
  id: number
  workflow_run_id: number
  target_key: string
  target_datetime: string | null
  status: string
}

const DateTargetWidget: React.FC<{ daysProp: number }> = ({ daysProp }) => {
  const [showTargets, setShowTargets] = useState(false)

  const complianceColor = (pct: number) => {
    if (pct >= 90) return '#28a745'
    if (pct >= 70) return '#ffc107'
    return '#dc3545'
  }

  const { data: stats, isLoading } = useQuery({
    queryKey: ['date-target-stats', daysProp],
    queryFn: async () => {
      const res = await dateTargetsApi.getStats(daysProp)
      return res.data as DateTargetStats
    },
    enabled: showTargets,
  })

  const { data: breached } = useQuery({
    queryKey: ['date-targets-breached'],
    queryFn: async () => {
      const res = await dateTargetsApi.list({ status: 'breached' })
      return res.data as DateTarget[]
    },
    enabled: showTargets,
  })

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div className="card-header">
        <h3 className="card-title">Date Targets</h3>
        <button
          className={`btn btn-sm ${showTargets ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShowTargets(!showTargets)}
        >
          {showTargets ? 'Hide' : 'View'}
        </button>
      </div>

      {showTargets && (
        <>
          {isLoading ? (
            <div className="loading">Loading date target stats...</div>
          ) : stats ? (
            <>
              {stats.total === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
                  No date targets in the selected period. Targets are created by workflow steps
                  configured with a <code>date_target_key</code> (e.g. the change-management demo).
                </div>
              ) : (
                <>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <div className="stat-value">{stats.total}</div>
                      <div className="stat-label">Total ({stats.period_days}d)</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: '#28a745' }}>{stats.met}</div>
                      <div className="stat-label">Met</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{ color: '#dc3545' }}>{stats.breached}</div>
                      <div className="stat-label">Breached</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{stats.pending}</div>
                      <div className="stat-label">Pending</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value" style={{
                        color: stats.compliance_pct == null ? undefined : complianceColor(stats.compliance_pct),
                        fontSize: '1.8rem'
                      }}>
                        {stats.compliance_pct == null ? '—' : `${stats.compliance_pct}%`}
                      </div>
                      <div className="stat-label">Compliance</div>
                    </div>
                  </div>

                  {breached && breached.length > 0 && (
                    <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
                      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem' }}>Breached Targets (all time)</h4>
                      <table className="table" style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Target Key</th>
                            <th>Due</th>
                            <th style={{ textAlign: 'right' }}>Run</th>
                          </tr>
                        </thead>
                        <tbody>
                          {breached.map((t) => (
                            <tr key={t.id}>
                              <td>{t.target_key}</td>
                              <td>{t.target_datetime ? new Date(t.target_datetime).toLocaleString() : '—'}</td>
                              <td style={{ textAlign: 'right' }}>
                                <Link to={`/runs/${t.workflow_run_id}`}>View run #{t.workflow_run_id}</Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

// D4: Hygiene Report Widget
const HygieneReportWidget: React.FC = () => {
  const [show, setShow] = useState(false)
  
  const { data, isLoading } = useQuery({
    queryKey: ['hygiene-report'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get('/api/admin/hygiene-report', {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as any
    },
    enabled: show,
  })

  if (!data) return null
  
  const { near_duplicates = [], unreferenced_forms = [], broken_references = [] } = data

  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <div className="card-header">
        <h3 className="card-title">Data Hygiene Report</h3>
        <button
          className={`btn btn-sm ${show ? 'btn-secondary' : 'btn-primary'}`}
          onClick={() => setShow(!show)}
        >
          {show ? 'Hide' : 'View'}
        </button>
      </div>

      {show && (
        <>
          {isLoading ? (
            <div className="loading">Loading hygiene report...</div>
          ) : (
            <div style={{ padding: '1rem' }}>
              {near_duplicates.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <h4 style={{ color: '#e74c3c', margin: '0 0 0.5rem' }}>⚠️ Near-Duplicate Names ({near_duplicates.length})</h4>
                  <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                    {near_duplicates.map((dup: any, i: number) => (
                      <li key={i} style={{ marginBottom: '0.25rem' }}>
                        "{dup.item1.name}" ↔ "{dup.item2.name}" ({dup.reason})
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {unreferenced_forms.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <h4 style={{ color: '#f39c12', margin: '0 0 0.5rem' }}>📋 Unreferenced Forms ({unreferenced_forms.length})</h4>
                  <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                    {unreferenced_forms.map((form: any, i: number) => (
                      <li key={i} style={{ marginBottom: '0.25rem' }}>
                        "{form.name}" — {form.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {broken_references.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <h4 style={{ color: '#e74c3c', margin: '0 0 0.5rem' }}>🔗 Broken References ({broken_references.length})</h4>
                  <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                    {broken_references.map((issue: any, i: number) => (
                      <li key={i} style={{ marginBottom: '0.25rem' }}>
                        {issue.type} "{issue.name}": {issue.issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {near_duplicates.length === 0 && unreferenced_forms.length === 0 && broken_references.length === 0 && (
                <div style={{ padding: '1rem', backgroundColor: '#d4edda', borderRadius: '4px' }}>
                  ✅ No hygiene issues found.
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
