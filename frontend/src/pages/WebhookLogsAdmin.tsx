import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../services/api'

interface WebhookLogRow {
  id: number
  direction: 'incoming' | 'outgoing'
  event_type: string
  status: string
  success: boolean
  workflow_id: number | null
  run_id: number | null
  tenant_id: number | null
  endpoint: string
  method: string
  source_ip: string
  idempotency_key: string
  attempt: number
  max_attempts: number
  will_retry: boolean
  status_code: number | null
  duration_ms: number | null
  detail: string
  response_snippet: string
  created_at: string
}

interface WebhookLogDetail extends WebhookLogRow {
  request_payload: unknown
}

interface WebhookLogList {
  items: WebhookLogRow[]
  total: number
  page: number
  page_size: number
}

interface WebhookLogStats {
  total: number
  incoming: number
  outgoing: number
  success: number
  failed: number
  retries: number
  avg_duration_ms: number | null
}

const PAGE_SIZE = 50

const statusClass = (row: WebhookLogRow) => {
  if (row.success) return 'badge-success'
  if (row.status === 'duplicate' || row.status === 'retry') return 'badge-info'
  return 'badge-danger'
}

export const WebhookLogsAdmin: React.FC = () => {
  const queryClient = useQueryClient()
  const [direction, setDirection] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [filters, setFilters] = useState({ direction: '', status: '', q: '' })
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data: logs, isLoading } = useQuery({
    queryKey: ['admin-webhook-logs', filters, page],
    queryFn: async () => {
      const response = await adminApi.listWebhookLogs({
        direction: filters.direction || undefined,
        status: filters.status || undefined,
        q: filters.q || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      return response.data as WebhookLogList
    },
  })

  const { data: stats } = useQuery({
    queryKey: ['admin-webhook-log-stats'],
    queryFn: async () => {
      const response = await adminApi.getWebhookLogStats(24)
      return response.data as WebhookLogStats
    },
    refetchInterval: 30000,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['admin-webhook-log-detail', selectedId],
    queryFn: async () => {
      const response = await adminApi.getWebhookLog(selectedId as number)
      return response.data as WebhookLogDetail
    },
    enabled: selectedId !== null,
  })

  const cleanupMutation = useMutation({
    mutationFn: (days: number) => adminApi.cleanupWebhookLogs(days),
    onSuccess: (response) => {
      alert(`Deleted ${response.data.deleted} old log entries.`)
      queryClient.invalidateQueries({ queryKey: ['admin-webhook-logs'] })
      queryClient.invalidateQueries({ queryKey: ['admin-webhook-log-stats'] })
    },
    onError: (err: any) => alert(err.response?.data?.detail || 'Cleanup failed'),
  })

  const items = useMemo(() => logs?.items || [], [logs])
  const totalPages = Math.max(1, Math.ceil((logs?.total || 0) / PAGE_SIZE))

  const applyFilters = (e: React.FormEvent) => {
    e.preventDefault()
    setFilters({ direction, status, q })
    setPage(1)
  }

  return (
    <div className="page-container">
      <h2>Webhook Execution Log</h2>
      <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
        Inbound invocations and outbound delivery attempts, including retries and idempotency keys.
        Payloads are redacted and size-capped before storage.
      </p>

      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', margin: '1rem 0' }}>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.total ?? '-'}</strong><div>Events (24h)</div></div>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.incoming ?? '-'}</strong><div>Incoming</div></div>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.outgoing ?? '-'}</strong><div>Outgoing</div></div>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.failed ?? '-'}</strong><div>Failed</div></div>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.retries ?? '-'}</strong><div>Retries</div></div>
        <div className="card" style={{ minWidth: '130px' }}><strong>{stats?.avg_duration_ms ?? '-'}{stats?.avg_duration_ms != null ? ' ms' : ''}</strong><div>Avg duration</div></div>
      </div>

      <form onSubmit={applyFilters} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <select className="form-input" style={{ maxWidth: '150px' }} value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="">All directions</option>
          <option value="incoming">Incoming</option>
          <option value="outgoing">Outgoing</option>
        </select>
        <select className="form-input" style={{ maxWidth: '150px' }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="rejected">Rejected</option>
          <option value="duplicate">Duplicate</option>
          <option value="retry">Retry</option>
        </select>
        <input
          className="form-input"
          style={{ maxWidth: '300px' }}
          placeholder="Search endpoint / detail / key..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button type="submit" className="btn btn-primary">Filter</button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            setDirection(''); setStatus(''); setQ('')
            setFilters({ direction: '', status: '', q: '' }); setPage(1)
          }}
        >
          Clear
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto' }}
          onClick={() => {
            if (window.confirm('Delete webhook log entries older than 30 days?')) {
              cleanupMutation.mutate(30)
            }
          }}
          disabled={cleanupMutation.isPending}
        >
          Cleanup old logs
        </button>
      </form>

      {isLoading ? (
        <p>Loading webhook logs...</p>
      ) : items.length === 0 ? (
        <p style={{ color: '#7f8c8d' }}>No webhook events recorded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Direction</th>
              <th>Event</th>
              <th>Status</th>
              <th>Endpoint</th>
              <th>Attempt</th>
              <th>HTTP</th>
              <th>Duration</th>
              <th>Run</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.created_at).toLocaleString()}</td>
                <td>{row.direction}</td>
                <td>{row.event_type}</td>
                <td><span className={`badge ${statusClass(row)}`}>{row.status}</span></td>
                <td title={row.endpoint} style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.endpoint}</td>
                <td>{row.attempt}/{row.max_attempts}{row.will_retry ? ' (retry)' : ''}</td>
                <td>{row.status_code ?? '-'}</td>
                <td>{row.duration_ms != null ? `${row.duration_ms} ms` : '-'}</td>
                <td>{row.run_id != null ? <a href={`/runs/${row.run_id}`}>#{row.run_id}</a> : '-'}</td>
                <td><button type="button" className="btn btn-sm btn-primary" onClick={() => setSelectedId(row.id)}>Details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '1rem' }}>
        <button type="button" className="btn btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
        <span>Page {page} of {totalPages} — {logs?.total ?? 0} events</span>
        <button type="button" className="btn btn-secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
      </div>

      {selectedId !== null && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Event #{selectedId}</h3>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => setSelectedId(null)}>Close</button>
          </div>
          {detailLoading ? <p>Loading...</p> : detail && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
              <div><strong>Source IP:</strong> {detail.source_ip || '-'}</div>
              <div><strong>Idempotency key:</strong> {detail.idempotency_key || '-'}</div>
              <div><strong>Workflow:</strong> {detail.workflow_id ?? '-'}</div>
              <div><strong>Tenant:</strong> {detail.tenant_id ?? 'system'}</div>
              <div style={{ gridColumn: '1 / -1' }}><strong>Detail:</strong> {detail.detail || '-'}</div>
              {detail.response_snippet && <div style={{ gridColumn: '1 / -1' }}><strong>Response:</strong> {detail.response_snippet}</div>}
              <div style={{ gridColumn: '1 / -1' }}>
                <strong>Request payload (redacted):</strong>
                <pre style={{ background: '#f4f6f7', padding: '0.75rem', overflowX: 'auto' }}>
                  {JSON.stringify(detail.request_payload, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
