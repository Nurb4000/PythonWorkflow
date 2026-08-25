import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { cmdbApi } from '../services/api'

interface CIType {
  id: number
  name: string
  key: string
  icon: string
  is_active?: boolean
  field_schema: FieldSchemaEntry[]
}

interface FieldSchemaEntry {
  key: string
  label: string
  type: string
  required: boolean
  options?: string[]
}

interface CIItem {
  id: number
  type_id: number
  name: string
  status: string
  ci_data: Record<string, any>
  custom_data: Record<string, any>
  type_name: string
  type_key: string
  created_by: number | null
  updated_by: number | null
  created_at: string
  updated_at: string
}

interface CIHistoryEntry {
  id: number
  ci_id: number
  changed_by: number | null
  changed_at: string
  field_key: string | null
  old_value: any
  new_value: any
  change_type: string
}

const STATUS_OPTIONS = ['active', 'maintenance', 'retired', 'decommissioned']

export const CItemList: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedTypeId, setSelectedTypeId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [searchQuery, setSearchQuery] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [viewMode, setViewMode] = useState<'edit' | 'view'>('edit')
  const [editingItem, setEditingItem] = useState<CIItem | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [formName, setFormName] = useState('')
  const [formStatus, setFormStatus] = useState('active')
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [showHistory, setShowHistory] = useState(false)

  const { data: types, isLoading: typesLoading } = useQuery<CIType[]>({
    queryKey: ['cmdb-types'],
    queryFn: () => cmdbApi.listTypes().then(r => {
      const d = r.data as any
      return (d.items || d) as CIType[]
    }),
  })

  const { data: items, isLoading: itemsLoading } = useQuery<CIItem[]>({
    queryKey: ['cmdb-items', selectedTypeId, statusFilter, searchQuery],
    queryFn: async () => {
      const params: any = {}
      if (selectedTypeId) params.type_id = selectedTypeId
      if (statusFilter) params.status = statusFilter
      if (!statusFilter) params.include_inactive = true
      if (searchQuery) params.search = searchQuery
      const res = await cmdbApi.listItems(params)
      const d = res.data as any
      return (d.items || d) as CIItem[]
    },
  })

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['cmdb-history', editingItem?.id],
    queryFn: async () => {
      if (!editingItem) return []
      const res = await cmdbApi.getItemHistory(editingItem.id)
      return res.data as CIHistoryEntry[]
    },
    enabled: !!editingItem && showHistory,
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => cmdbApi.createItem(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-items'] })
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setShowForm(false)
      resetForm()
      setSuccess('CI created successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create CI')
      setTimeout(() => setError(''), 5000)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => cmdbApi.updateItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-items'] })
      setShowForm(false)
      setEditingItem(null)
      resetForm()
      setSuccess('CI updated successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update CI')
      setTimeout(() => setError(''), 5000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => cmdbApi.deleteItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-items'] })
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setSuccess('CI deleted')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete CI')
      setTimeout(() => setError(''), 5000)
    },
  })

  const currentType = useMemo(() => types?.find(t => t.id === selectedTypeId), [types, selectedTypeId])

  // For viewing/editing an item, resolve its type even if no filter is set
  const itemType = useMemo(() => {
    if (!editingItem || !types) return null
    return types.find(t => t.id === editingItem.type_id) || null
  }, [editingItem, types])

  const resetForm = () => {
    setFormName('')
    setFormStatus('active')
    setFormData({})
    setEditingItem(null)
    setShowHistory(false)
  }

  const handleCreate = () => {
    if (!selectedTypeId) {
      setError('Select a CI type first')
      setTimeout(() => setError(''), 3000)
      return
    }
    resetForm()
    setShowForm(true)
    setError('')
  }

  const handleEdit = (item: CIItem) => {
    setEditingItem(item)
    setFormName(item.name)
    setFormStatus(item.status)
    setFormData({ ...item.ci_data })
    setViewMode('edit')
    setShowForm(true)
    setShowHistory(false)
    setError('')
  }

  const handleView = (item: CIItem) => {
    setEditingItem(item)
    setFormName(item.name)
    setFormStatus(item.status)
    setFormData({ ...item.ci_data })
    setViewMode('view')
    setShowForm(true)
    setShowHistory(false)
    setError('')
  }

  const handleSubmit = () => {
    if (!formName.trim()) {
      setError('Name is required')
      return
    }
    if (editingItem) {
      updateMutation.mutate({ id: editingItem.id, data: { name: formName, status: formStatus, ci_data: formData } })
    } else {
      createMutation.mutate({ type_id: selectedTypeId, name: formName, status: formStatus, ci_data: formData })
    }
  }

  const handleDelete = (item: CIItem) => {
    if (confirm(`Delete CI "${item.name}"?`)) {
      deleteMutation.mutate(item.id)
    }
  }

  const renderFieldInput = (field: FieldSchemaEntry, value: any) => {
    switch (field.type) {
      case 'number':
        return (
          <input
            type="number"
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value === '' ? '' : Number(e.target.value) }))}
            style={{ fontSize: '0.85rem' }}
          />
        )
      case 'boolean':
        return (
          <select
            className="form-input"
            value={value ? 'true' : 'false'}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value === 'true' }))}
            style={{ fontSize: '0.85rem' }}
          >
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        )
      case 'date':
        return (
          <input
            type="date"
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
            style={{ fontSize: '0.85rem' }}
          />
        )
      case 'datetime':
        return (
          <input
            type="datetime-local"
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
            style={{ fontSize: '0.85rem' }}
          />
        )
      case 'select':
        return (
          <select
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
            style={{ fontSize: '0.85rem' }}
          >
            <option value="">— select —</option>
            {(field.options || []).map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        )
      case 'text':
        return (
          <textarea
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
            rows={2}
            style={{ fontSize: '0.85rem' }}
          />
        )
      default:
        return (
          <input
            type="text"
            className="form-input"
            value={value ?? ''}
            onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
            style={{ fontSize: '0.85rem' }}
          />
        )
    }
  }

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      active: '#28a745',
      maintenance: '#ffc107',
      retired: '#6c757d',
      decommissioned: '#dc3545',
    }
    return (
      <span style={{
        padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem',
        backgroundColor: colors[status] || '#6c757d', color: status === 'maintenance' ? '#000' : '#fff'
      }}>
        {status}
      </span>
    )
  }

  const loading = typesLoading || itemsLoading

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2>CMDB — Configuration Items</h2>
        {selectedTypeId && !showForm && (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-primary" onClick={handleCreate}>+ New Item</button>
            <Link to={`/cmdb/items/bulk-import/${currentType?.key}`} className="btn btn-secondary">Bulk Import</Link>
            <button className="btn btn-secondary" onClick={() => {
              cmdbApi.exportItems(selectedTypeId, 'csv').then(res => {
                const url = window.URL.createObjectURL(new Blob([res.data]))
                const link = document.createElement('a')
                link.href = url
                link.setAttribute('download', `ci_export_${selectedTypeId}.csv`)
                document.body.appendChild(link)
                link.click()
                link.remove()
              })
            }}>Export CSV</button>
          </div>
        )}
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {success && <div style={{ marginBottom: '1rem', padding: '0.5rem', borderRadius: '4px', backgroundColor: '#d4edda', color: '#155724' }}>{success}</div>}

      {/* Type selector */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title">Filter</h3>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0, flex: 1, minWidth: '200px' }}>
            <label className="form-label">CI Type</label>
            <select
              className="form-input"
              value={selectedTypeId ?? ''}
              onChange={e => setSelectedTypeId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">All Types</option>
              {types?.filter(t => t.is_active !== false).map(t => (
                <option key={t.id} value={t.id}>{t.icon ? t.icon + ' ' : ''}{t.name}</option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, minWidth: '150px' }}>
            <label className="form-label">Status</label>
            <select
              className="form-input"
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
            >
              {STATUS_OPTIONS.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
              <option value="">All</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0, flex: 2, minWidth: '200px' }}>
            <label className="form-label">Search</label>
            <input
              type="text"
              className="form-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search by name..."
            />
          </div>
          {(selectedTypeId || statusFilter !== 'active' || searchQuery) && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSelectedTypeId(null); setStatusFilter('active'); setSearchQuery('') }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Create/Edit form */}
      {showForm && (editingItem ? itemType : currentType) && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              {viewMode === 'view'
                ? `View: ${(itemType || currentType)!.name}`
                : editingItem
                  ? `Edit: ${(itemType || currentType)!.name}`
                  : `New: ${(currentType!)!.name}`}
            </span>
            {viewMode === 'view' && editingItem && (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <Link to={`/cmdb/items/${editingItem.id}/relationships`} className="btn btn-sm btn-secondary">
                  Relationships
                </Link>
                <Link to={`/cmdb/items/${editingItem.id}/graph`} className="btn btn-sm btn-primary">
                  Dependency Graph
                </Link>
              </div>
            )}
          </h3>

          <div className="form-group">
            <label className="form-label">Name *</label>
            {viewMode === 'view' ? (
              <div style={{ padding: '0.5rem', fontSize: '1rem', fontWeight: 500 }}>{formName}</div>
            ) : (
              <input
                type="text"
                className="form-input"
                value={formName}
                onChange={e => setFormName(e.target.value)}
                placeholder="e.g. web-prod-01"
              />
            )}
          </div>

          <div className="form-group">
            <label className="form-label">Status</label>
            {viewMode === 'view' ? (
              <div style={{ padding: '0.5rem 0' }}>{statusBadge(formStatus)}</div>
            ) : (
              <select
                className="form-input"
                value={formStatus}
                onChange={e => setFormStatus(e.target.value)}
              >
                {STATUS_OPTIONS.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '0.75rem', marginTop: '1rem' }}>
            {((itemType || currentType)!.field_schema || []).map(field => (
              <div key={field.key} className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">
                  {field.label}{field.required && ' *'}
                </label>
                {viewMode === 'view' ? (
                  <div style={{ padding: '0.5rem', fontSize: '0.85rem', color: formData[field.key] ? '#333' : '#999' }}>
                    {formData[field.key] ?? '—'}
                  </div>
                ) : (
                  renderFieldInput(field, formData[field.key])
                )}
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            {viewMode === 'edit' && (
              <>
                <button
                  className="btn btn-primary"
                  onClick={handleSubmit}
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {createMutation.isPending || updateMutation.isPending ? 'Saving...' : (editingItem ? 'Update' : 'Create')}
                </button>
                <button className="btn btn-secondary" onClick={() => { setShowForm(false); resetForm() }}>Cancel</button>
              </>
            )}
            {viewMode === 'view' && editingItem && (
              <>
                <button className="btn btn-primary" onClick={() => setViewMode('edit')}>Edit</button>
                <button className="btn btn-secondary" onClick={() => { setShowForm(false); resetForm() }}>Close</button>
              </>
            )}
          </div>
        </div>
      )}

      {/* History timeline */}
      {editingItem && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3 className="card-title">Change History</h3>
            <button
              className={`btn btn-sm ${showHistory ? 'btn-secondary' : 'btn-primary'}`}
              onClick={() => setShowHistory(!showHistory)}
            >
              {showHistory ? 'Hide History' : 'View History'}
            </button>
          </div>

          {showHistory && (
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {historyLoading ? (
                <div className="loading" style={{ padding: '1rem' }}>Loading history...</div>
              ) : history && history.length > 0 ? (
                <div style={{ position: 'relative', paddingLeft: '1.5rem' }}>
                  <div style={{ position: 'absolute', left: '0.6rem', top: 0, bottom: 0, width: '2px', backgroundColor: '#dee2e6' }} />
                  {history.map((entry, idx) => (
                    <div key={entry.id} style={{ position: 'relative', marginBottom: '1rem', paddingLeft: '1rem' }}>
                      <div style={{
                        position: 'absolute', left: '-1.75rem', top: '0.25rem',
                        width: '12px', height: '12px', borderRadius: '50%',
                        backgroundColor: entry.change_type === 'create' ? '#28a745' : entry.change_type === 'delete' ? '#dc3545' : '#007bff',
                        border: '2px solid #fff',
                      }} />
                      <div style={{ fontSize: '0.8rem', color: '#6c757d' }}>
                        {new Date(entry.changed_at).toLocaleString()} · By user #{entry.changed_by}
                        <span style={{
                          display: 'inline-block', marginLeft: '0.5rem', padding: '1px 6px',
                          borderRadius: '8px', fontSize: '0.7rem', textTransform: 'uppercase',
                          backgroundColor: entry.change_type === 'create' ? '#d4edda' : entry.change_type === 'delete' ? '#f8d7da' : '#cce5ff',
                          color: entry.change_type === 'create' ? '#155724' : entry.change_type === 'delete' ? '#721c24' : '#004085',
                        }}>
                          {entry.change_type}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                        {entry.field_key ? (
                          <span>
                            <strong>{entry.field_key}</strong>:{' '}
                            {entry.old_value !== null && entry.old_value !== undefined ? String(entry.old_value) : '—'}
                            {' → '}
                            {entry.new_value !== null && entry.new_value !== undefined ? String(entry.new_value) : '—'}
                          </span>
                        ) : (
                          <span>
                            {entry.change_type === 'create' ? `CI created with ${Object.keys(entry.new_value || {}).length} fields` :
                             entry.change_type === 'delete' ? 'CI deleted' : 'CI modified'}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ padding: '1rem', textAlign: 'center', color: '#6c757d' }}>No change history recorded.</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Items list — hidden while viewing/editing an item */}
      {!editingItem && (loading ? (
        <div className="loading">Loading items...</div>
      ) : (
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          {items?.map(item => (
            <div key={item.id} className="card" style={{ position: 'relative' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <h4 style={{ margin: '0 0 0.25rem 0' }}>
                    {item.name} {statusBadge(item.status)}
                  </h4>
                  <p style={{ margin: '0 0 0.5rem 0', color: '#6c757d', fontSize: '0.85rem' }}>
                    Type: {item.type_name} ({item.type_key}) · ID: {item.id}
                  </p>
                  {item.ci_data && Object.keys(item.ci_data).length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {Object.entries(item.ci_data).map(([k, v]) => (
                        <span key={k} style={{ fontSize: '0.8rem' }}>
                          <strong>{k}:</strong> {String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-sm btn-secondary" onClick={() => handleView(item)}>View</button>
                  <button className="btn btn-sm btn-primary" onClick={() => handleEdit(item)}>Edit</button>
                  <button className="btn btn-sm" style={{ color: '#dc3545' }} onClick={() => handleDelete(item)}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}

      {!loading && !editingItem && items && items.length === 0 && (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6c757d' }}>
          <p>No configuration items found.</p>
          {selectedTypeId && <p>Select a type and click "+ New Item" to create one.</p>}
          {!selectedTypeId && <p>Select a CI type from the filter above.</p>}
        </div>
      )}
    </div>
  )
}
