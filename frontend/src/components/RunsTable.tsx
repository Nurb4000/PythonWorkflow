import React, { useEffect, useMemo, useRef, useState } from 'react'

export interface ColumnDef {
  key: string
  label: string
  render?: (row: any) => React.ReactNode
  csv?: (row: any) => string
  hideable?: boolean
}

interface RunsTableProps {
  rows: any[]
  columns: ColumnDef[]
  storageKey: string
  actions?: (row: any) => React.ReactNode
  emptyMessage?: string
}

export const RunsTable: React.FC<RunsTableProps> = ({
  rows,
  columns,
  storageKey,
  actions,
  emptyMessage = 'No records found'
}) => {
  const [search, setSearch] = useState('')
  const [showColMenu, setShowColMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const defaultVisible = columns.filter(c => c.hideable !== false).map(c => c.key)
  const [visible, setVisible] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(`columns:${storageKey}`)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed)) return parsed
      }
    } catch {
      // ignore corrupt cache
    }
    return defaultVisible
  })

  useEffect(() => {
    localStorage.setItem(`columns:${storageKey}`, JSON.stringify(visible))
  }, [visible, storageKey])

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowColMenu(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const cellValue = (row: any, col: ColumnDef): string => {
    if (col.csv) return col.csv(row)
    if (col.render) {
      const rendered = col.render(row)
      if (rendered === null || rendered === undefined) return ''
      return String(rendered)
    }
    const raw = row[col.key]
    return raw === null || raw === undefined ? '' : String(raw)
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(row =>
      columns.some(col => cellValue(row, col).toLowerCase().includes(q))
    )
  }, [rows, search, columns])

  const toggleColumn = (key: string) => {
    setVisible(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    )
  }

  const exportCsv = () => {
    const visCols = columns.filter(c => visible.includes(c.key))
    const header = visCols.map(c => `"${c.label.replace(/"/g, '""')}"`).join(',')
    const lines = filtered.map(row =>
      visCols.map(c => `"${cellValue(row, c).replace(/"/g, '""')}"`).join(',')
    )
    const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${storageKey}_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const visibleColumns = columns.filter(c => visible.includes(c.key))
  const colSpan = visibleColumns.length + (actions ? 1 : 0)

  return (
    <div>
      <div className="card-header" style={{ flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            className="form-input"
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: '240px' }}
          />
          <div style={{ position: 'relative' }} ref={menuRef}>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setShowColMenu(!showColMenu)}
            >
              Columns
            </button>
            {showColMenu && (
              <div
                style={{
                  position: 'absolute',
                  zIndex: 20,
                  top: '100%',
                  left: 0,
                  background: 'white',
                  border: '1px solid #ddd',
                  borderRadius: '6px',
                  padding: '0.5rem 0.75rem',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
                  minWidth: '170px'
                }}
              >
                {columns.map(c => (
                  <label
                    key={c.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      padding: '0.2rem 0',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={visible.includes(c.key)}
                      onChange={() => toggleColumn(c.key)}
                    />
                    {c.label}
                  </label>
                ))}
              </div>
            )}
          </div>
          <button className="btn btn-sm btn-primary" onClick={exportCsv}>
            Export CSV
          </button>
          <span style={{ opacity: 0.7, fontSize: '0.85rem', marginLeft: '0.5rem' }}>
            {filtered.length} of {rows.length} record{rows.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      <table className="table">
        <thead>
          <tr>
            {visibleColumns.map(c => <th key={c.key}>{c.label}</th>)}
            {actions && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr>
              <td colSpan={colSpan} style={{ textAlign: 'center', padding: '2rem', opacity: 0.6 }}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            filtered.map((row, i) => (
              <tr key={row.id ?? i}>
                {visibleColumns.map(c => (
                  <td key={c.key}>{c.render ? c.render(row) : row[c.key] ?? '-'}</td>
                ))}
                {actions && <td>{actions(row)}</td>}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
