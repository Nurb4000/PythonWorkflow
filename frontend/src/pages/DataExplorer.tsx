import React, { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dataQueryApi, dataExportApi, aiApi } from '../services/api'

interface TableInfo {
  table: string
  display_name: string
  native_columns: Array<{ name: string; type: string; is_pk?: boolean }>
  relationship_columns: Array<{
    fk_column: string
    target_table: string
    target_display: string
    available_columns: Array<{ name: string; type: string; is_pk?: boolean }>
  }>
  custom_fields: Array<{
    id: number
    field_key: string
    label: string
    field_type: string
    scope: string
    scope_id: number | null
    config: any
  }>
  error?: string
}

interface FilterRow {
  id: number
  mode: 'native' | 'custom' | 'relationship'
  column: string
  rel_chain: Array<{ target_table: string; fk_column: string }>
  operator: string
  value: string
}

const OPERATORS = [
  { value: '=', label: 'Equals' },
  { value: '!=', label: 'Not Equals' },
  { value: '>', label: 'Greater Than' },
  { value: '<', label: 'Less Than' },
  { value: '>=', label: 'Greater Or Equal' },
  { value: '<=', label: 'Less Or Equal' },
  { value: 'contains', label: 'Contains' },
  { value: 'starts_with', label: 'Starts With' },
  { value: 'ends_with', label: 'Ends With' },
  { value: 'is_null', label: 'Is Null / Not Null' },
  { value: 'in', label: 'In (comma-separated)' },
]

export const DataExplorer: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'visual' | 'sql'>('visual')
  const [selectedTable, setSelectedTable] = useState('')
  const [logic, setLogic] = useState('AND')
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState('desc')
  const [limit, setLimit] = useState(100)
  const [offset, setOffset] = useState(0)
  const [sql, setSql] = useState('')
  const [filters, setFilters] = useState<FilterRow[]>([{ id: 1, mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }])
  const [error, setError] = useState('')

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

  const currentTable = tables?.find(t => t.table === selectedTable)

  const { data: queryResult, isLoading: loadingQuery } = useQuery({
    queryKey: ['data-query', selectedTable, filters, logic, sortBy, sortOrder, limit, offset],
    queryFn: async () => {
      if (!selectedTable) return null
      const filterPayload = filters.map(f => ({
        field: f.column,
        operator: f.operator,
        value: f.value,
        is_custom: f.mode === 'custom',
        relationship_chain: f.rel_chain,
      }))
      const res = await dataQueryApi.runVisual({
        table: selectedTable,
        filters: filterPayload,
        logic,
        sort_by: sortBy || undefined,
        sort_order: sortOrder,
        limit,
        offset,
      })
      return res.data
    },
    enabled: !!selectedTable && activeTab === 'visual',
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

  const addFilter = useCallback(() => {
    setFilters(prev => [...prev, { id: Date.now(), mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }])
  }, [])

  const removeFilter = (id: number) => {
    setFilters(prev => prev.filter(f => f.id !== id))
  }

  const updateFilter = (id: number, updates: Partial<FilterRow>) => {
    setFilters(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f))
  }

  const addRelChain = (filterId: number) => {
    if (!currentTable) return
    setFilters(prev => prev.map(f => {
      if (f.id !== filterId) return f
      const rels = currentTable.relationship_columns
      return { ...f, rel_chain: [...f.rel_chain, { target_table: '', fk_column: '' }]
      }
    }))
  }

  const updateRelChain = (filterId: number, idx: number, updates: any) => {
    setFilters(prev => prev.map(f => {
      if (f.id !== filterId) return f
      const chain = [...f.rel_chain]
      chain[idx] = { ...chain[idx], ...updates }
      return { ...f, rel_chain: chain }
    }))
  }

  const removeRelChain = (filterId: number, idx: number) => {
    setFilters(prev => prev.map(f => {
      if (f.id !== filterId) return f
      return { ...f, rel_chain: f.rel_chain.filter((_, i) => i !== idx) }
    }))
  }

  const handleExportCsv = async () => {
    setError('')
    try {
      let blob: Blob
      if (activeTab === 'visual' && selectedTable) {
        const filterPayload = filters.map(f => ({
          field: f.column,
          operator: f.operator,
          value: f.value,
          is_custom: f.mode === 'custom',
          relationship_chain: f.rel_chain,
        }))
        const res = await dataExportApi.exportQuery({
          table: selectedTable,
          filters: filterPayload,
          logic,
          sort_by: sortBy || undefined,
          sort_order: sortOrder,
          limit: 10000,
        })
        blob = res.data
      } else {
        const res = await dataExportApi.exportTable(selectedTable)
        blob = res.data
      }

      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${selectedTable}_export.csv`)
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
      const res = await dataExportApi.exportTable(selectedTable)
      const blob = res.data
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${selectedTable}_full_export.csv`)
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
        table: selectedTable || undefined,
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
    if (!aiQueryPrompt.trim() || !selectedTable) return
    setAiQueryLoading(true)
    setAiQueryError('')
    try {
      const res = await aiApi.assistQuery({
        action: 'generate',
        description: aiQueryPrompt,
        table: selectedTable,
        available_columns: currentTable?.native_columns,
      })
      const generatedSql = res.data.result?.sql || ''
      const whereMatch = generatedSql.match(/WHERE\s+(.+?)(?:\s+ORDER\s|LIMIT|$)/i)
      if (whereMatch) {
        const conditions = whereMatch[1].split(/\s+AND\s+/i)
        const newFilters: typeof filters = []
        for (const cond of conditions) {
          const parts = cond.trim().split(/\s+/)
          if (parts.length >= 3) {
            const col = parts[0]
            const op = parts[1].replace(/['"]/g, '')
            const val = parts.slice(2).join(' ').replace(/['"]/g, '')
            newFilters.push({
              id: Date.now() + Math.random(),
              mode: 'native' as const,
              column: col,
              rel_chain: [],
              operator: op,
              value: val,
            })
          }
        }
        if (newFilters.length > 0) {
          setFilters(newFilters)
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
          {selectedTable && !tablesError && (
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
        <div className="card">
          <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Table *</label>
              <select
                className="form-select"
                value={selectedTable}
                onChange={(e) => { setSelectedTable(e.target.value); setOffset(0); }}
              >
                <option value="">Select a table...</option>
                {(tables || []).map(t => (
                  <option key={t.table} value={t.table}>{t.display_name}</option>
                ))}
              </select>
            </div>

            {selectedTable && (
              <>
                {currentTable?.error && (
                  <div className="error" style={{ gridColumn: '1 / -1', marginBottom: '0.5rem' }}>
                    Error loading "{currentTable.display_name}": {currentTable.error}
                  </div>
                )}
                {!currentTable?.error && currentTable && currentTable.native_columns.length === 0 && (
                  <div style={{ gridColumn: '1 / -1', padding: '0.5rem', background: '#fff3cd', borderRadius: '4px', fontSize: '0.875rem' }}>
                    No columns found for "{currentTable.display_name}". The table may not exist or has no accessible fields.
                  </div>
                )}
                <div className="form-group">
                  <label className="form-label">Sort By</label>
                  <select
                    className="form-select"
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                  >
                    <option value="">No sort</option>
                    {(currentTable?.native_columns || []).map(c => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                    {(currentTable?.custom_fields || []).map(c => (
                      <option key={c.field_key} value={c.field_key}>{c.label} (custom)</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Sort Order</label>
                  <select className="form-select" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
                    <option value="asc">Ascending</option>
                    <option value="desc">Descending</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Limit</label>
                  <input type="number" className="form-input" value={limit} onChange={(e) => setLimit(parseInt(e.target.value) || 100)} min={1} max={10000} />
                </div>
              </>
            )}
          </div>

          {selectedTable && (
            <>
              <div style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <strong>Filters</strong>
                <button className="btn btn-sm btn-secondary" onClick={() => setLogic(logic === 'AND' ? 'OR' : 'AND')}>
                  Logic: {logic}
                </button>
                <button className="btn btn-sm btn-primary" onClick={addFilter}>+ Add Filter</button>
              </div>

              {/* AI to Filters */}
              <div style={{ marginBottom: '0.75rem', padding: '0.5rem', background: '#fef9e7', borderRadius: '4px', border: '1px solid #f9e79f' }}>
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

              {filters.map((f, fi) => (
                <div key={f.id} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <select
                    className="form-select"
                    value={f.mode}
                    onChange={(e) => updateFilter(f.id, { mode: e.target.value as any, column: '', rel_chain: [] })}
                    style={{ width: '140px', flexShrink: 0 }}
                  >
                    <option value="native">Column</option>
                    <option value="custom">Custom Field</option>
                    {currentTable?.relationship_columns.length ? <option value="relationship">Related</option> : null}
                  </select>

                  {f.mode === 'native' && (
                    <select
                      className="form-select"
                      value={f.column}
                      onChange={(e) => updateFilter(f.id, { column: e.target.value })}
                      style={{ flex: 1, minWidth: '150px' }}
                    >
                      <option value="">Select column...</option>
                      {(currentTable?.native_columns || []).map(c => (
                        <option key={c.name} value={c.name}>{c.name}</option>
                      ))}
                    </select>
                  )}

                  {f.mode === 'custom' && (
                    <select
                      className="form-select"
                      value={f.column}
                      onChange={(e) => updateFilter(f.id, { column: e.target.value })}
                      style={{ flex: 1, minWidth: '150px' }}
                    >
                      <option value="">Select custom field...</option>
                      {(currentTable?.custom_fields || []).map(c => (
                        <option key={c.field_key} value={c.field_key}>{c.label}</option>
                      ))}
                    </select>
                  )}

                  {f.mode === 'relationship' && (
                    <>
                      <select
                        className="form-select"
                        value={f.column}
                        onChange={(e) => updateFilter(f.id, { column: e.target.value, rel_chain: f.rel_chain.length ? f.rel_chain : [{ target_table: '', fk_column: '' }] })}
                        style={{ flex: 1, minWidth: '150px' }}
                      >
                        <option value="">Select related column...</option>
                        {(currentTable?.relationship_columns || []).map(rc =>
                          rc.available_columns.map(ac => (
                            <option key={`${rc.target_table}.${ac.name}`} value={`${rc.target_table}.${ac.name}`}>
                              {rc.target_display} &gt; {ac.name}
                            </option>
                          ))
                        )}
                      </select>
                    </>
                  )}

                  <select
                    className="form-select"
                    value={f.operator}
                    onChange={(e) => updateFilter(f.id, { operator: e.target.value })}
                    style={{ width: '150px', flexShrink: 0 }}
                  >
                    {OPERATORS.map(op => (
                      <option key={op.value} value={op.value}>{op.label}</option>
                    ))}
                  </select>

                  {!f.operator.includes('null') && (
                    <input
                      type="text"
                      className="form-input"
                      value={f.value}
                      onChange={(e) => updateFilter(f.id, { value: e.target.value })}
                      placeholder="Value"
                      style={{ flex: 1, minWidth: '120px' }}
                    />
                  )}

                  {f.operator === 'is_null' && (
                    <select
                      className="form-select"
                      value={f.value}
                      onChange={(e) => updateFilter(f.id, { value: e.target.value })}
                      style={{ width: '120px', flexShrink: 0 }}
                    >
                      <option value="">Is Null</option>
                      <option value="true">Is Not Null</option>
                    </select>
                  )}

                  {filters.length > 1 && (
                    <button className="btn btn-sm btn-danger" onClick={() => removeFilter(f.id)}>X</button>
                  )}
                </div>
              ))}

              <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={() => { setOffset(0); queryClient.invalidateQueries({ queryKey: ['data-query'] }) }}>
                Run Query
              </button>
            </>
          )}
        </div>
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

          {selectedTable && (
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

          {selectedTable && (
            <div style={{ marginTop: '1rem' }}>
              <small style={{ color: '#7f8c8d' }}>Quick queries for "{currentTable?.display_name}":</small>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                <button className="btn btn-sm btn-secondary" onClick={() => setSql(`SELECT * FROM ${selectedTable} LIMIT 50;`)}>
                  First 50 rows
                </button>
                <button className="btn btn-sm btn-secondary" onClick={() => setSql(`SELECT COUNT(*) FROM ${selectedTable};`)}>
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
            {results.total > limit && (
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  Previous
                </button>
                <span style={{ fontSize: '0.875rem', color: '#7f8c8d' }}>
                  Page {Math.floor(offset / limit) + 1}
                </span>
                <button
                  className="btn btn-sm btn-secondary"
                  disabled={offset + limit >= (results.total || 0)}
                  onClick={() => setOffset(offset + limit)}
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
                {results.items.slice(0, limit).map((row: any, idx: number) => (
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

      {!loading && !results && selectedTable && activeTab === 'visual' && (
        <div className="card" style={{ marginTop: '1rem', textAlign: 'center', color: '#7f8c8d' }}>
          Configure filters above and click "Run Query" to see results.
        </div>
      )}
        </>
      )}
    </div>
  )
}
