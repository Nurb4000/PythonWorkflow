import React, { useState, useCallback } from 'react'

export interface TableInfo {
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

export interface FilterRow {
  id: number
  mode: 'native' | 'custom' | 'relationship'
  column: string
  rel_chain: Array<{ target_table: string; fk_column: string }>
  operator: string
  value: string
}

export interface VisualQuery {
  table: string
  filters: FilterRow[]
  logic: 'AND' | 'OR'
  sortBy: string
  sortOrder: 'asc' | 'desc'
  limit: number
}

export const OPERATORS = [
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

interface QueryBuilderProps {
  tables: TableInfo[]
  value: VisualQuery
  onChange: (query: VisualQuery) => void
  onRun?: () => void
  showRunButton?: boolean
}

export const QueryBuilder: React.FC<QueryBuilderProps> = ({
  tables,
  value,
  onChange,
  onRun,
  showRunButton = false,
}) => {
  const currentTable = tables?.find(t => t.table === value.table)

  const update = useCallback((updates: Partial<VisualQuery>) => {
    onChange({ ...value, ...updates })
  }, [value, onChange])

  const addFilter = useCallback(() => {
    update({
      filters: [...value.filters, { id: Date.now(), mode: 'native', column: '', rel_chain: [], operator: '=', value: '' }],
    })
  }, [value, update])

  const removeFilter = useCallback((id: number) => {
    update({ filters: value.filters.filter(f => f.id !== id) })
  }, [value, update])

  const updateFilter = useCallback((id: number, patch: Partial<FilterRow>) => {
    update({
      filters: value.filters.map(f => f.id === id ? { ...f, ...patch } : f),
    })
  }, [value, update])

  if (!value.table) {
    return (
      <div className="card">
        <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Table *</label>
            <select
              className="form-select"
              value={value.table}
              onChange={(e) => update({ table: e.target.value, sortBy: '', sortOrder: 'desc', limit: 100 })}
            >
              <option value="">Select a table...</option>
              {(tables || []).map(t => (
                <option key={t.table} value={t.table}>{t.display_name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      {currentTable?.error && (
        <div className="error" style={{ marginBottom: '0.5rem' }}>
          Error loading "{currentTable.display_name}": {currentTable.error}
        </div>
      )}

      {!currentTable?.error && currentTable && currentTable.native_columns.length === 0 && (
        <div style={{ marginBottom: '0.5rem', padding: '0.5rem', background: '#fff3cd', borderRadius: '4px', fontSize: '0.875rem' }}>
          No columns found for "{currentTable.display_name}". The table may not exist or has no accessible fields.
        </div>
      )}

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <div className="form-group">
          <label className="form-label">Table</label>
          <select
            className="form-select"
            value={value.table}
            onChange={(e) => update({ table: e.target.value, sortBy: '', sortOrder: 'desc', limit: 100 })}
          >
            {(tables || []).map(t => (
              <option key={t.table} value={t.table}>{t.display_name}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Sort By</label>
          <select
            className="form-select"
            value={value.sortBy}
            onChange={(e) => update({ sortBy: e.target.value })}
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
          <select className="form-select" value={value.sortOrder} onChange={(e) => update({ sortOrder: e.target.value })}>
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Limit</label>
          <input
            type="number"
            className="form-input"
            value={value.limit}
            onChange={(e) => update({ limit: parseInt(e.target.value) || 100 })}
            min={1}
            max={10000}
          />
        </div>
      </div>

      <div style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <strong>Filters</strong>
        <button className="btn btn-sm btn-secondary" onClick={() => update({ logic: value.logic === 'AND' ? 'OR' : 'AND' })}>
          Logic: {value.logic}
        </button>
        <button className="btn btn-sm btn-primary" onClick={addFilter}>+ Add Filter</button>
      </div>

      {value.filters.map((f) => (
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

          {value.filters.length > 1 && (
            <button className="btn btn-sm btn-danger" onClick={() => removeFilter(f.id)}>X</button>
          )}
        </div>
      ))}

      {showRunButton && onRun && (
        <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={onRun}>
          Run Query
        </button>
      )}
    </div>
  )
}
