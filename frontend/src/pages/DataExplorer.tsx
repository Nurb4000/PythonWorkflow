import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dataQueryApi, dataExportApi, aiApi } from '../services/api'
import { QueryBuilder, VisualQuery, TableInfo } from '../components/QueryBuilder'

const DEFAULT_QUERY: VisualQuery = {
  table: '',
  filters: [{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
  logic: 'AND',
  sortBy: '',
  sortOrder: 'desc',
  limit: 100,
}

export const DataExplorer: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'visual' | 'sql'>('visual')
  const [offset, setOffset] = useState(0)
  const [sql, setSql] = useState('')
  const [error, setError] = useState('')
  const [visualQuery, setVisualQuery] = useState<VisualQuery>(DEFAULT_QUERY)

  // AI query assist state
  const [aiQueryPrompt, setAiQueryPrompt] = useState('')
  const [aiQueryLoading, setAiQueryLoading] = useState(false)
  const [aiQueryResponse, setAiQueryResponse] = useState<any>(null)
  const [aiQueryError, setAiQueryError] = useState('')

  const { data: tables, isLoading: loadingTables, error: tablesError } = useQuery({
    queryKey: ['data-tables'],
    queryFn: async () => {
      const res = await dataQueryApi.listTables()
      return res.data as TableInfo[]
    },
  })

  const currentTable = tables?.find(t => t.table === visualQuery.table)

  const buildFilterPayload = (filters: VisualQuery['filters']) => filters.map(f => ({
    field: f.column,
    operator: f.operator,
    value: f.value,
    is_custom: f.mode === 'custom',
    relationship_chain: f.rel_chain,
  }))

  const { data: queryResult, isLoading: loadingQuery } = useQuery({
    queryKey: ['data-query', visualQuery.table, visualQuery.filters, visualQuery.logic, visualQuery.sortBy, visualQuery.sortOrder, visualQuery.limit, offset],
    queryFn: async () => {
      if (!visualQuery.table) return null
      const res = await dataQueryApi.runVisual({
        table: visualQuery.table,
        filters: buildFilterPayload(visualQuery.filters),
        logic: visualQuery.logic,
        sort_by: visualQuery.sortBy || undefined,
        sort_order: visualQuery.sortOrder,
        limit: visualQuery.limit,
        offset,
      })
      return res.data
    },
    enabled: !!visualQuery.table && activeTab === 'visual',
  })

  const { data: sqlResult, isLoading: loadingSql } = useQuery({
    queryKey: ['data-sql', sql],
    queryFn: async () => {
      if (!sql.trim()) return null
      const res = await dataQueryApi.runSql({ sql })
      return res.data
    },
    enabled: !!sql.trim() && activeTab === 'sql',
  })

  const handleExportCsv = async () => {
    setError('')
    try {
      let blob: Blob
      if (activeTab === 'visual' && visualQuery.table) {
        const res = await dataExportApi.exportQuery({
          table: visualQuery.table,
          filters: buildFilterPayload(visualQuery.filters),
          logic: visualQuery.logic,
          sort_by: visualQuery.sortBy || undefined,
          sort_order: visualQuery.sortOrder,
          limit: 10000,
        })
        blob = res.data
      } else {
        const res = await dataExportApi.exportTable(visualQuery.table)
        blob = res.data
      }

      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${visualQuery.table}_export.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Export failed')
    }
  }

  const handleExportFullTable = async () => {
    setError('')
    try {
      const res = await dataExportApi.exportTable(visualQuery.table)
      const blob = res.data
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${visualQuery.table}_full_export.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Export failed')
    }
  }

  // AI query assist handlers
  const handleAiGenerateSql = async () => {
    if (!aiQueryPrompt.trim()) return
    setAiQueryLoading(true)
    setAiQueryError('')
    setAiQueryResponse(null)
    try {
      const res = await aiApi.assistQuery({
        action: 'generate',
        description: aiQueryPrompt,
        table: visualQuery.table || undefined,
        available_columns: currentTable?.native_columns,
      })
      setAiQueryResponse(res.data.result)
      if (res.data.result?.sql) {
        setSql(res.data.result.sql)
      }
    } catch (err: any) {
      setAiQueryError(err.response?.data?.detail || 'AI query generation failed')
    } finally {
      setAiQueryLoading(false)
    }
  }

  const handleAiExplainSql = async () => {
    if (!sql.trim()) return
    setAiQueryLoading(true)
    setAiQueryError('')
    setAiQueryResponse(null)
    try {
      const res = await aiApi.assistQuery({
        action: 'explain',
        sql,
      })
      setAiQueryResponse(res.data.result)
    } catch (err: any) {
      setAiQueryError(err.response?.data?.detail || 'AI explanation failed')
    } finally {
      setAiQueryLoading(false)
    }
  }

  const handleAiFixSql = async () => {
    if (!sql.trim()) return
    setAiQueryLoading(true)
    setAiQueryError('')
    setAiQueryResponse(null)
    try {
      const res = await aiApi.assistQuery({
        action: 'fix',
        sql,
        error_message: error || 'Query execution failed',
      })
      setAiQueryResponse(res.data.result)
      if (res.data.result?.fixed_sql) {
        setSql(res.data.result.fixed_sql)
      }
    } catch (err: any) {
      setAiQueryError(err.response?.data?.detail || 'AI fix failed')
    } finally {
      setAiQueryLoading(false)
    }
  }

  const handleAiToFilters = async () => {
    if (!aiQueryPrompt.trim() || !visualQuery.table) return
    setAiQueryLoading(true)
    setAiQueryError('')
    try {
      const res = await aiApi.assistQuery({
        action: 'generate',
        description: aiQueryPrompt,
        table: visualQuery.table,
        available_columns: currentTable?.native_columns,
      })
      const generatedSql = res.data.result?.sql || ''
      const whereMatch = generatedSql.match(/WHERE\s+(.+?)(?:\s+ORDER\s|LIMIT|$)/i)
      if (whereMatch) {
        const conditions = whereMatch[1].split(/\s+AND\s+/i)
        const newFilters: typeof visualQuery.filters = []
        for (const cond of conditions) {
          const parts = cond.trim().split(/\s+/)
          if (parts.length >= 3) {
            const col = parts[0]
            const op = parts[1].replace(/['"]/g, '')
            const val = parts.slice(2).join(' ').replace(/['"]/g, '')
            newFilters.push({
              id: Date.now() + Math.random(),
              mode: 'native',
              column: col,
              rel_chain: [],
              operator: op,
              value: val,
            })
          }
        }
        if (newFilters.length > 0) {
          setVisualQuery(prev => ({ ...prev, filters: newFilters }))
        }
      }
    } catch (err: any) {
      setAiQueryError(err.response?.data?.detail || 'AI filter generation failed')
    } finally {
      setAiQueryLoading(false)
    }
  }

  if (loadingTables) return <div className="loading">Loading tables...</div>

  const results = activeTab === 'visual' ? queryResult : sqlResult
  const loading = activeTab === 'visual' ? loadingQuery : loadingSql

  return (
    <div>
      <div className="card-header">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Link to="/admin" className="btn btn-sm btn-secondary" style={{ fontSize: '0.85rem' }}>← Back</Link>
          Data Explorer
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {visualQuery.table && !tablesError && (
            <>
              <button className="btn btn-sm btn-success" onClick={handleExportCsv} disabled={!results}>
                Export Results to CSV
              </button>
              <button className="btn btn-sm btn-primary" onClick={handleExportFullTable}>
                Export Full Table
              </button>
            </>
          )}
        </div>
      </div>

      {tablesError && (
        <div className="error">
          Failed to load tables: {tablesError.message || String(tablesError)}. Make sure you're logged in as admin or developer.
        </div>
      )}

      {error && !tablesError && <div className="error">{error}</div>}

      {!tablesError && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <button
              className={`btn ${activeTab === 'visual' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveTab('visual')}
            >
              Visual Builder
            </button>
            <button
              className={`btn ${activeTab === 'sql' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveTab('sql')}
            >
              SQL Editor
            </button>
          </div>

          {activeTab === 'visual' && (
            <>
              <QueryBuilder
                tables={tables || []}
                value={visualQuery}
                onChange={setVisualQuery}
                onRun={() => { setOffset(0); queryClient.invalidateQueries({ queryKey: ['data-query'] }) }}
                showRunButton
              />

              {/* AI to Filters */}
              {visualQuery.table && (
                <div className="card" style={{ marginTop: '1rem' }}>
                  <div style={{ padding: '0.5rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f' }}>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input
                        className="form-input"
                        type="text"
                        value={aiQueryPrompt}
                        onChange={(e) => setAiQueryPrompt(e.target.value)}
                        placeholder="AI: Describe filters you need..."
                        style={{ flex: 1, fontSize: '0.85rem' }}
                      />
                      <button
                        className="btn btn-warning btn-sm"
                        onClick={handleAiToFilters}
                        disabled={aiQueryLoading || !aiQueryPrompt.trim()}
                      >
                        {aiQueryLoading ? '...' : 'AI to Filters'}
                      </button>
                    </div>
                    {aiQueryError && <div className="error" style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>{aiQueryError}</div>}
                  </div>
                </div>
              )}
            </>
          )}

          {activeTab === 'sql' && (
            <div className="card">
              <div style={{ marginBottom: '0.5rem', padding: '0.75rem', background: '#fff3cd', borderRadius: '4px', fontSize: '0.875rem' }}>
                <strong>Read-only:</strong> Only SELECT queries are allowed. Queries timeout after 30 seconds and are limited to 10,000 rows.
              </div>

              {/* AI Assist Panel */}
              <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '6px', border: '1px solid #f9e79f' }}>
                <label className="form-label">AI Query Assist</label>
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <input
                    className="form-input"
                    type="text"
                    value={aiQueryPrompt}
                    onChange={(e) => setAiQueryPrompt(e.target.value)}
                    placeholder="Describe the query you need..."
                    style={{ flex: 1 }}
                  />
                  <button
                    className="btn btn-warning btn-sm"
                    onClick={handleAiGenerateSql}
                    disabled={aiQueryLoading || !aiQueryPrompt.trim()}
                  >
                    {aiQueryLoading ? '...' : 'Generate SQL'}
                  </button>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="btn btn-info btn-sm"
                    onClick={handleAiExplainSql}
                    disabled={aiQueryLoading || !sql.trim()}
                  >
                    Explain Query
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleAiFixSql}
                    disabled={aiQueryLoading || !sql.trim()}
                  >
                    Fix Errors
                  </button>
                </div>
                {aiQueryError && <div className="error" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>{aiQueryError}</div>}
                {aiQueryResponse && aiQueryResponse.action !== 'generate' && (
                  <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: '#fff', borderRadius: '4px', border: '1px solid #ddd', fontSize: '0.85rem' }}>
                    {aiQueryResponse.explanation && <p>{aiQueryResponse.explanation}</p>}
                    {aiQueryResponse.tables_used?.length > 0 && <p><strong>Tables:</strong> {aiQueryResponse.tables_used.join(', ')}</p>}
                    {aiQueryResponse.filters_applied && <p><strong>Filters:</strong> {aiQueryResponse.filters_applied}</p>}
                    {aiQueryResponse.notes && <p><strong>Notes:</strong> {aiQueryResponse.notes}</p>}
                    {aiQueryResponse.fixed_sql && (
                      <>
                        <p><strong>Fixed SQL:</strong></p>
                        <pre style={{ whiteSpace: 'pre-wrap', background: '#f8f9fa', padding: '0.5rem', borderRadius: '4px' }}>{aiQueryResponse.fixed_sql}</pre>
                      </>
                    )}
                  </div>
                )}
              </div>

              {visualQuery.table && (
                <div style={{ marginBottom: '1rem', padding: '0.5rem', background: '#f8f9fa', borderRadius: '4px', fontSize: '0.875rem' }}>
                  <strong>Available tables:</strong>{' '}
                  {(tables || []).map(t => (
                    <code key={t.table} style={{ margin: '0 0.25rem' }}>{t.table}</code>
                  ))}
                </div>
              )}

              <textarea
                className="form-textarea"
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                placeholder="SELECT * FROM tasks WHERE status = 'open' LIMIT 50;"
                rows={6}
                style={{ fontFamily: 'monospace', marginBottom: '1rem' }}
              />

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-primary" onClick={() => queryClient.invalidateQueries({ queryKey: ['data-sql'] })}>
                  Run Query
                </button>
                <button className="btn btn-secondary" onClick={() => setSql('')}>Clear</button>
              </div>

              {visualQuery.table && (
                <div style={{ marginTop: '1rem' }}>
                  <small style={{ color: '#7f8c8d' }}>Quick queries for "{currentTable?.display_name}":</small>
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                    <button className="btn btn-sm btn-secondary" onClick={() => setSql(`SELECT * FROM ${visualQuery.table} LIMIT 50;`)}>
                      First 50 rows
                    </button>
                    <button className="btn btn-sm btn-secondary" onClick={() => setSql(`SELECT COUNT(*) FROM ${visualQuery.table};`)}>
                      Count rows
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {loading && <div className="loading">Running query...</div>}

          {results && results.items && (
            <div className="card" style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 className="card-title">Results ({results.total} total)</h3>
                {results.total > visualQuery.limit && (
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <button
                      className="btn btn-sm btn-secondary"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - visualQuery.limit))}
                    >
                      Previous
                    </button>
                    <span style={{ fontSize: '0.875rem', color: '#7f8c8d' }}>
                      Page {Math.floor(offset / visualQuery.limit) + 1}
                    </span>
                    <button
                      className="btn btn-sm btn-secondary"
                      disabled={offset + visualQuery.limit >= (results.total || 0)}
                      onClick={() => setOffset(offset + visualQuery.limit)}
                    >
                      Next
                    </button>
                  </div>
                )}
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      {(results.columns || (results.items[0] ? Object.keys(results.items[0]) : [])).map((col: string) => (
                        <th key={col} style={{ whiteSpace: 'nowrap' }}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {results.items.slice(0, visualQuery.limit).map((row: any, idx: number) => (
                      <tr key={idx}>
                        {(results.columns || Object.keys(row)).map((col: string) => (
                          <td key={col} style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {row[col] === null ? <span style={{ color: '#aaa' }}>NULL</span> :
                             row[col] === undefined ? '-' :
                             typeof row[col] === 'object' ? JSON.stringify(row[col]).substring(0, 100) :
                             String(row[col]).substring(0, 200)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!loading && !results && visualQuery.table && activeTab === 'visual' && (
            <div className="card" style={{ marginTop: '1rem', textAlign: 'center', color: '#7f8c8d' }}>
              Configure filters above and click "Run Query" to see results.
            </div>
          )}
        </>
      )}
    </div>
  )
}
