/**
 * Visual Report Builder — Drag-and-drop report definition tool.
 *
 * F1 adds a "Run & visualize" panel: the existing /reports/{id}/execute
 * endpoint supplies rows, and dependency-free SVG charts render them without
 * changing the report schema or the definition editor.
 */
import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { ReportCharts, ReportChartType } from '../components/ReportCharts'

const API_URL = '/api'

interface ReportDefinition {
  id: number
  name: string
  description: string
  view_name?: string
  columns: any[]
  filters: any[]
  sort_by: string
  sort_order: string
  limit: number
  schedule_cron?: string
  export_format: string
  is_active: boolean
}

interface ReportResult {
  report_id: number
  name: string
  columns: string[]
  rows: Array<Record<string, any>>
  total_rows: number
}

const COUNT_MODE = '__count__'

const errorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    return detail || error.message
  }
  return 'Report execution failed.'
}

export const ReportBuilder: React.FC = () => {
  const queryClient = useQueryClient()
  const [editingReport, setEditingReport] = useState<ReportDefinition | null>(null)
  const [result, setResult] = useState<ReportResult | null>(null)
  const [chartType, setChartType] = useState<ReportChartType>('bar')
  const [labelField, setLabelField] = useState('')
  const [valueField, setValueField] = useState('')
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    view_name: '',
    columns: [] as any[],
    filters: [] as any[],
    sort_by: '',
    sort_order: 'asc',
    limit: 100,
    schedule_cron: '',
    export_format: 'csv',
    is_active: true
  })

  const { data: reports } = useQuery({
    queryKey: ['reports'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/reports`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data.items as ReportDefinition[]
    }
  })

  const createMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const token = localStorage.getItem('token')
      return await axios.post(`${API_URL}/reports/`, data, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      resetForm()
    }
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: typeof formData }) => {
      const token = localStorage.getItem('token')
      return await axios.put(`${API_URL}/reports/${id}`, data, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      resetForm()
    }
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const token = localStorage.getItem('token')
      return await axios.delete(`${API_URL}/reports/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      setResult((current) => current?.report_id === undefined ? current : null)
    }
  })

  const executeMutation = useMutation({
    mutationFn: async (id: number) => {
      const token = localStorage.getItem('token')
      const res = await axios.post(`${API_URL}/reports/${id}/execute`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return res.data as ReportResult
    },
    onSuccess: (data) => {
      setResult(data)
      setLabelField('')
      setValueField('')
    }
  })

  const resultColumns = useMemo(
    () => result?.columns?.length
      ? result.columns
      : Object.keys(result?.rows?.[0] || {}),
    [result]
  )

  const numericColumns = useMemo(
    () => resultColumns.filter((column) =>
      (result?.rows || []).some((row) => typeof row[column] === 'number')
    ),
    [result, resultColumns]
  )

  // Aggregate before charting: repeated category labels (or a count-only
  // result) become one bar/slice/point per label.
  const chartData = useMemo(() => {
    if (!result || !resultColumns.length) return { labels: [] as string[], values: [] as number[] }
    const label = labelField || resultColumns[0]
    const countMode = valueField === COUNT_MODE || (!valueField && !numericColumns.length)
    const value = countMode ? '' : (valueField || numericColumns[0])
    const grouped = new Map<string, number>()
    for (const row of result.rows) {
      const key = String(row[label] ?? '(blank)')
      const measure = countMode ? 1 : Number(row[value])
      if (!countMode && !Number.isFinite(measure)) continue
      grouped.set(key, (grouped.get(key) || 0) + measure)
    }
    return {
      labels: Array.from(grouped.keys()),
      values: Array.from(grouped.values()),
    }
  }, [result, resultColumns, labelField, valueField, numericColumns])

  const resetForm = () => {
    setEditingReport(null)
    setFormData({
      name: '',
      description: '',
      view_name: '',
      columns: [],
      filters: [],
      sort_by: '',
      sort_order: 'asc',
      limit: 100,
      schedule_cron: '',
      export_format: 'csv',
      is_active: true
    })
  }

  const handleEdit = (report: ReportDefinition) => {
    setEditingReport(report)
    setFormData({
      name: report.name,
      description: report.description,
      view_name: report.view_name || '',
      columns: report.columns || [],
      filters: report.filters || [],
      sort_by: report.sort_by || '',
      sort_order: report.sort_order || 'asc',
      limit: report.limit || 100,
      schedule_cron: report.schedule_cron || '',
      export_format: report.export_format || 'csv',
      is_active: report.is_active
    })
  }

  const handleSave = () => {
    if (editingReport) {
      updateMutation.mutate({ id: editingReport.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  return (
    <div style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>Report Builder</h2>
        <button className="btn btn-primary" onClick={resetForm}>
          {editingReport ? 'Cancel' : '+ New Report'}
        </button>
      </div>

      {/* Report List */}
      {!editingReport && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Existing Reports</h3>
          {reports?.map(report => (
            <div key={report.id} className="card report-list-row" style={{ marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong>{report.name}</strong>
                <div style={{ fontSize: '0.85rem', color: '#666' }}>{report.description}</div>
              </div>
              <div className="report-row-actions" style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => executeMutation.mutate(report.id)}
                  disabled={executeMutation.isPending}
                >
                  {executeMutation.isPending ? 'Running...' : 'Run'}
                </button>
                <button className="btn btn-sm btn-secondary" onClick={() => handleEdit(report)}>Edit</button>
                <button className="btn btn-sm btn-danger" onClick={() => {
                  if (confirm(`Delete report "${report.name}"?`)) {
                    deleteMutation.mutate(report.id)
                  }
                }}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* F1: execution results + charts */}
      {!editingReport && executeMutation.isError && (
        <div className="report-error" role="alert">
          {errorMessage(executeMutation.error)}
        </div>
      )}
      {!editingReport && result && (
        <div className="card report-results" style={{ marginBottom: '2rem' }}>
          <div className="card-header">
            <h3 className="card-title">{result.name} — results</h3>
            <span className="stat-label">{result.total_rows} rows</span>
          </div>
          <div style={{ padding: '1rem' }}>
            <div className="report-chart-controls">
              <label>
                Chart
                <select
                  className="form-input"
                  value={chartType}
                  onChange={(e) => setChartType(e.target.value as ReportChartType)}
                >
                  <option value="bar">Bar</option>
                  <option value="line">Line</option>
                  <option value="donut">Donut</option>
                </select>
              </label>
              <label>
                Label
                <select
                  className="form-input"
                  value={labelField || resultColumns[0] || ''}
                  onChange={(e) => setLabelField(e.target.value)}
                >
                  {resultColumns.map((column) => (
                    <option key={column} value={column}>{column}</option>
                  ))}
                </select>
              </label>
              <label>
                Value
                <select
                  className="form-input"
                  value={valueField}
                  onChange={(e) => setValueField(e.target.value)}
                >
                  <option value="">Auto</option>
                  {numericColumns.map((column) => (
                    <option key={column} value={column}>{column}</option>
                  ))}
                  <option value={COUNT_MODE}>Count rows</option>
                </select>
              </label>
            </div>

            <ReportCharts
              type={chartType}
              labels={chartData.labels}
              values={chartData.values}
              title={`${result.name}: ${labelField || resultColumns[0] || 'label'}`}
            />

            <details className="report-raw-rows">
              <summary>View raw rows</summary>
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>{resultColumns.map((column) => <th key={column}>{column}</th>)}</tr>
                  </thead>
                  <tbody>
                    {result.rows.slice(0, 50).map((row, index) => (
                      <tr key={index}>
                        {resultColumns.map((column) => (
                          <td key={column}>{String(row[column] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        </div>
      )}

      {/* Report Editor */}
      {editingReport && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Edit Report: {editingReport.name}</h3>
          </div>
          <div style={{ padding: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Report Name</label>
              <input
                type="text"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                placeholder="e.g., Weekly Server Inventory"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-textarea"
                value={formData.description}
                onChange={(e) => setFormData({...formData, description: e.target.value})}
                rows={3}
                placeholder="What does this report show?"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Source View</label>
              <input
                type="text"
                className="form-input"
                value={formData.view_name}
                onChange={(e) => setFormData({...formData, view_name: e.target.value})}
                placeholder="e.g., v_ci_server"
              />
              <small style={{ color: '#666' }}>SQL VIEW name (e.g., v_form_*, v_ci_*)</small>
            </div>

            <div className="form-group">
              <label className="form-label">Columns (JSON array)</label>
              <textarea
                className="form-textarea"
                value={JSON.stringify(formData.columns, null, 2)}
                onChange={(e) => {
                  try {
                    setFormData({...formData, columns: JSON.parse(e.target.value)})
                  } catch (err) {
                    // Ignore invalid JSON
                  }
                }}
                rows={6}
                placeholder='[{"field": "name", "label": "Server Name"}]'
              />
            </div>

            <div className="form-group">
              <label className="form-label">Filters (JSON array)</label>
              <textarea
                className="form-textarea"
                value={JSON.stringify(formData.filters, null, 2)}
                onChange={(e) => {
                  try {
                    setFormData({...formData, filters: JSON.parse(e.target.value)})
                  } catch (err) {
                    // Ignore invalid JSON
                  }
                }}
                rows={4}
                placeholder='[{"column": "status", "operator": "=", "value": "active"}]'
              />
            </div>

            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">Sort By</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.sort_by}
                  onChange={(e) => setFormData({...formData, sort_by: e.target.value})}
                  placeholder="column_name"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Sort Order</label>
                <select
                  className="form-input"
                  value={formData.sort_order}
                  onChange={(e) => setFormData({...formData, sort_order: e.target.value})}
                >
                  <option value="asc">Ascending</option>
                  <option value="desc">Descending</option>
                </select>
              </div>
            </div>

            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">Limit</label>
                <input
                  type="number"
                  className="form-input"
                  value={formData.limit}
                  onChange={(e) => setFormData({...formData, limit: parseInt(e.target.value) || 100})}
                  min={1}
                  max={10000}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Export Format</label>
                <select
                  className="form-input"
                  value={formData.export_format}
                  onChange={(e) => setFormData({...formData, export_format: e.target.value})}
                >
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                  <option value="excel">Excel</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Schedule Cron (optional)</label>
              <input
                type="text"
                className="form-input"
                value={formData.schedule_cron}
                onChange={(e) => setFormData({...formData, schedule_cron: e.target.value})}
                placeholder="e.g., 0 9 * * 1 (Monday at 9 AM)"
              />
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

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-success" onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save Report'}
              </button>
              <button className="btn btn-secondary" onClick={resetForm}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
