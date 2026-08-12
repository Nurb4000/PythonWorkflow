import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { useAuth } from '../components/Auth'

interface FieldSchemaEntry {
  key: string
  label: string
  type: string
  required: boolean
  options: string[]
  validation?: string | null
  help_text?: string | null
}

interface CIType {
  id: number
  name: string
  key: string
  description: string
  icon: string
  field_schema: FieldSchemaEntry[]
  is_active: boolean
  item_count: number
  created_at: string
  updated_at: string
}

const FIELD_TYPES = [
  { value: 'string', label: 'Text (Short)' },
  { value: 'text', label: 'Text (Long)' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'date', label: 'Date' },
  { value: 'datetime', label: 'Date & Time' },
  { value: 'select', label: 'Dropdown (Select)' },
  { value: 'email', label: 'Email' },
  { value: 'url', label: 'URL' },
]

const emptyField: FieldSchemaEntry = {
  key: '',
  label: '',
  type: 'string',
  required: false,
  options: [],
}

export const CITypeManager: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    icon: '',
    field_schema: [] as FieldSchemaEntry[],
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [optionInput, setOptionInput] = useState<Record<number, string>>({})
  const [showTemplates, setShowTemplates] = useState(false)
  const [activeFilter, setActiveFilter] = useState<'active' | 'inactive' | 'all'>('active')

  const { data: types, isLoading } = useQuery({
    queryKey: ['cmdb-types'],
    queryFn: () => cmdbApi.listTypes().then(r => r.data as CIType[]),
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => cmdbApi.createType(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setShowForm(false)
      resetForm()
      setSuccess('CI type created successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create CI type')
      setTimeout(() => setError(''), 5000)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => cmdbApi.updateType(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setShowForm(false)
      setEditingId(null)
      resetForm()
      setSuccess('CI type updated successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update CI type')
      setTimeout(() => setError(''), 5000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => cmdbApi.deleteType(id),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      queryClient.invalidateQueries({ queryKey: ['cmdb-items'] })
      const msg = data?.items_deactivated > 0
        ? `CI type deactivated. ${data.items_deactivated} item(s) set to retired.`
        : 'CI type deactivated'
      setSuccess(msg)
      setTimeout(() => setSuccess(''), 5000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to deactivate CI type')
      setTimeout(() => setError(''), 5000)
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: (id: number) => cmdbApi.updateType(id, { is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setSuccess('CI type reactivated')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to reactivate CI type')
      setTimeout(() => setError(''), 5000)
    },
  })

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['cmdb-templates'],
    queryFn: () => cmdbApi.listTemplates().then(r => r.data as any[]),
    enabled: showTemplates,
  })

  const applyTemplateMutation = useMutation({
    mutationFn: (key: string) => cmdbApi.applyTemplate(key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cmdb-types'] })
      setSuccess('Template applied successfully')
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to apply template')
      setTimeout(() => setError(''), 5000)
    },
  })

  const resetForm = () => {
    setFormData({ name: '', description: '', icon: '', field_schema: [] })
    setOptionInput({})
  }

  const handleCreate = () => {
    if (!isAdmin) return
    resetForm()
    setEditingId(null)
    setShowForm(true)
    setError('')
  }

  const handleEdit = (type: CIType) => {
    if (!isAdmin) return
    setFormData({
      name: type.name,
      description: type.description || '',
      icon: type.icon || '',
      field_schema: type.field_schema ? [...type.field_schema] : [],
    })
    setEditingId(type.id)
    setShowForm(true)
    setError('')
  }

  const handleSubmit = () => {
    if (!formData.name.trim()) {
      setError('Name is required')
      return
    }
    const payload = {
      name: formData.name.trim(),
      description: formData.description,
      icon: formData.icon,
      field_schema: formData.field_schema.map(f => ({
        key: f.key,
        label: f.label,
        type: f.type,
        required: f.required,
        options: f.options || [],
        validation: f.validation || null,
        help_text: f.help_text || null,
      })),
    }
    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const handleDelete = (type: CIType) => {
    if (!isAdmin) return
    let msg = `Deactivate CI type "${type.name}"?`
    if (type.item_count > 0) {
      msg += `\n\nThis type has ${type.item_count} item(s). They will also be set to "retired" status.`
    }
    if (confirm(msg)) {
      deleteMutation.mutate(type.id)
    }
  }

  const addField = () => {
    setFormData(prev => ({
      ...prev,
      field_schema: [...prev.field_schema, { ...emptyField }],
    }))
  }

  const removeField = (idx: number) => {
    setFormData(prev => ({
      ...prev,
      field_schema: prev.field_schema.filter((_, i) => i !== idx),
    }))
  }

  const updateField = (idx: number, updates: Partial<FieldSchemaEntry>) => {
    setFormData(prev => ({
      ...prev,
      field_schema: prev.field_schema.map((f, i) => i === idx ? { ...f, ...updates } : f),
    }))
  }

  const addOption = (fieldIdx: number) => {
    const val = optionInput[fieldIdx]?.trim()
    if (!val) return
    setFormData(prev => {
      const schema = [...prev.field_schema]
      const field = { ...schema[fieldIdx] }
      field.options = [...(field.options || []), val]
      schema[fieldIdx] = field
      return { ...prev, field_schema: schema }
    })
    setOptionInput(prev => ({ ...prev, [fieldIdx]: '' }))
  }

  const removeOption = (fieldIdx: number, optIdx: number) => {
    setFormData(prev => {
      const schema = [...prev.field_schema]
      const field = { ...schema[fieldIdx] }
      field.options = field.options.filter((_, i) => i !== optIdx)
      schema[fieldIdx] = field
      return { ...prev, field_schema: schema }
    })
  }

  if (isLoading) return <div className="loading">Loading CI types...</div>

  const filteredTypes = useMemo(() => {
    if (!types) return []
    if (activeFilter === 'active') return types.filter(t => t.is_active !== false)
    if (activeFilter === 'inactive') return types.filter(t => t.is_active === false)
    return types
  }, [types, activeFilter])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2>CMDB — CI Types</h2>
        {isAdmin && (
          <button className="btn btn-primary" onClick={handleCreate}>
            + New CI Type
          </button>
        )}
      </div>

      {/* Active/All filter */}
      <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <span style={{ fontSize: '0.9rem', color: '#6c757d' }}>Show:</span>
        <select
          className="form-select"
          value={activeFilter}
          onChange={e => setActiveFilter(e.target.value as any)}
          style={{ width: 'auto', minWidth: '180px', fontSize: '0.9rem' }}
        >
          <option value="active">Active ({types?.filter(t => t.is_active !== false).length || 0})</option>
          <option value="inactive">Inactive ({types?.filter(t => t.is_active === false).length || 0})</option>
          <option value="all">All ({types?.length || 0})</option>
        </select>
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {success && <div style={{ marginBottom: '1rem', padding: '0.5rem', borderRadius: '4px', backgroundColor: '#d4edda', color: '#155724' }}>{success}</div>}

      {!isAdmin && (
        <div style={{ marginBottom: '1rem', padding: '0.5rem', borderRadius: '4px', backgroundColor: '#fff3cd', color: '#856404', fontSize: '0.9rem' }}>
          Only admins can create or modify CI types. Contact your administrator to manage types.
        </div>
      )}

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 className="card-title">{editingId ? 'Edit CI Type' : 'New CI Type'}</h3>

          <div className="form-group">
            <label className="form-label">Name *</label>
            <input
              type="text"
              className="form-input"
              value={formData.name}
              onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g. Server, Network Device, Application"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea
              className="form-input"
              value={formData.description}
              onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
              rows={2}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Icon (emoji or short label)</label>
            <input
              type="text"
              className="form-input"
              value={formData.icon}
              onChange={e => setFormData(prev => ({ ...prev, icon: e.target.value }))}
              placeholder="e.g. 🖥️ or server"
              style={{ maxWidth: '200px' }}
            />
          </div>

          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h4 style={{ margin: 0 }}>Field Schema</h4>
              <button className="btn btn-sm btn-secondary" onClick={addField}>+ Add Field</button>
            </div>

            {formData.field_schema.map((field, idx) => (
              <div key={idx} style={{
                border: '1px solid #dee2e6', borderRadius: '6px', padding: '0.75rem', marginBottom: '0.75rem',
                backgroundColor: '#f8f9fa', position: 'relative'
              }}>
                <button
                  className="btn btn-sm"
                  style={{ position: 'absolute', top: '4px', right: '4px', color: '#dc3545' }}
                  onClick={() => removeField(idx)}
                  title="Remove field"
                >✕</button>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '0.5rem', alignItems: 'end' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Key *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={field.key}
                      onChange={e => updateField(idx, { key: e.target.value.replace(/\s+/g, '_').toLowerCase() })}
                      placeholder="hostname"
                      style={{ fontSize: '0.85rem' }}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Label *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={field.label}
                      onChange={e => updateField(idx, { label: e.target.value })}
                      placeholder="Hostname"
                      style={{ fontSize: '0.85rem' }}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Type</label>
                    <select
                      className="form-input"
                      value={field.type}
                      onChange={e => updateField(idx, { type: e.target.value })}
                      style={{ fontSize: '0.85rem' }}
                    >
                      {FIELD_TYPES.map(ft => (
                        <option key={ft.value} value={ft.value}>{ft.label}</option>
                      ))}
                    </select>
                  </div>
                  <label style={{ fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px', paddingBottom: '6px' }}>
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={e => updateField(idx, { required: e.target.checked })}
                    />
                    Required
                  </label>
                </div>

                {field.type === 'select' && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Options</label>
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.25rem' }}>
                      <input
                        type="text"
                        className="form-input"
                        value={optionInput[idx] || ''}
                        onChange={e => setOptionInput(prev => ({ ...prev, [idx]: e.target.value }))}
                        placeholder="Add option..."
                        style={{ fontSize: '0.85rem', flex: 1 }}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addOption(idx) } }}
                      />
                      <button className="btn btn-sm btn-secondary" onClick={() => addOption(idx)}>Add</button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                      {(field.options || []).map((opt, oi) => (
                        <span key={oi} style={{
                          display: 'inline-flex', alignItems: 'center', gap: '4px',
                          padding: '2px 8px', borderRadius: '12px', fontSize: '0.8rem',
                          backgroundColor: '#e9ecef', color: '#495057'
                        }}>
                          {opt}
                          <span style={{ cursor: 'pointer', fontWeight: 'bold' }} onClick={() => removeOption(idx, oi)}>×</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {field.type === 'string' && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <label className="form-label" style={{ fontSize: '0.8rem' }}>Validation (optional)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={field.validation || ''}
                      onChange={e => updateField(idx, { validation: e.target.value })}
                      placeholder="e.g. ipv4, email, hostname"
                      style={{ fontSize: '0.85rem', maxWidth: '300px' }}
                    />
                  </div>
                )}
              </div>
            ))}

            {formData.field_schema.length === 0 && (
              <p style={{ color: '#6c757d', fontSize: '0.9rem' }}>No fields defined yet. Click "+ Add Field" to start building the schema.</p>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving...' : (editingId ? 'Update' : 'Create')}
            </button>
            <button className="btn btn-secondary" onClick={() => { setShowForm(false); resetForm() }}>Cancel</button>
          </div>
        </div>
      )}

      {/* Templates section — hidden when form is open */}
      {!showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <h3 className="card-title">Pre-built Templates</h3>
          <button
            className={`btn btn-sm ${showTemplates ? 'btn-secondary' : 'btn-primary'}`}
            onClick={() => setShowTemplates(!showTemplates)}
          >
            {showTemplates ? 'Hide Templates' : 'Show Templates'}
          </button>
        </div>

        {showTemplates && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem', marginTop: '0.75rem' }}>
            {templatesLoading ? (
              <div className="loading">Loading templates...</div>
            ) : templates?.map((template: any) => {
              const exists = types?.some(t => t.key === template.key)
              return (
                <div key={template.key} style={{
                  border: '1px solid #dee2e6', borderRadius: '8px', padding: '1rem',
                  backgroundColor: exists ? '#f8f9fa' : '#fff',
                  opacity: exists ? 0.7 : 1,
                }}>
                  <h4 style={{ margin: '0 0 0.25rem 0', fontSize: '1rem' }}>
                    {template.icon && <span style={{ marginRight: '0.5rem' }}>{template.icon}</span>}
                    {template.name}
                    {exists && <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: '#6c757d' }}>(exists)</span>}
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#6c757d' }}>
                    {template.description} · {template.field_schema?.length || 0} fields
                  </p>
                  {isAdmin && (
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => applyTemplateMutation.mutate(template.key)}
                      disabled={exists || applyTemplateMutation.isPending}
                    >
                      {exists ? 'Already Exists' : applyTemplateMutation.isPending ? 'Applying...' : 'Apply Template'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
        )}

      <div style={{ display: 'grid', gap: '1rem' }}>
        {filteredTypes.map(type => (
          <div key={type.id} className="card" style={{ position: 'relative', opacity: type.is_active === false ? 0.65 : 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3 style={{ margin: '0 0 0.25rem 0' }}>
                  {type.icon && <span style={{ marginRight: '0.5rem' }}>{type.icon}</span>}
                  {type.name}
                  {!type.is_active && <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: '#dc3545' }}>(inactive)</span>}
                </h3>
                <p style={{ margin: '0 0 0.5rem 0', color: '#6c757d', fontSize: '0.9rem' }}>
                  key: <code>{type.key}</code> · {type.item_count} item(s)
                  {type.description && ` · ${type.description}`}
                </p>
                {type.field_schema && type.field_schema.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                    {type.field_schema.map((f, i) => (
                      <span key={i} style={{
                        padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem',
                        backgroundColor: f.required ? '#cce5ff' : '#e9ecef',
                        color: f.required ? '#004085' : '#495057'
                      }}>
                        {f.label} ({f.type}){f.required && ' *'}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {isAdmin && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  {type.is_active === false ? (
                    <button
                      className="btn btn-sm btn-success"
                      onClick={() => {
                        if (confirm(`Reactivate CI type "${type.name}"?`)) {
                          reactivateMutation.mutate(type.id)
                        }
                      }}
                      disabled={reactivateMutation.isPending}
                    >
                      Reactivate
                    </button>
                  ) : (
                    <>
                      <button className="btn btn-sm btn-secondary" onClick={() => handleEdit(type)}>Edit</button>
                      <button className="btn btn-sm" style={{ color: '#dc3545' }} onClick={() => handleDelete(type)}>Deactivate</button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {filteredTypes.length === 0 && !showForm && (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6c757d' }}>
          {activeFilter === 'active' && types && types.length > 0
            ? <p>No active CI types. Switch to "All" or "Inactive" to see them.</p>
            : activeFilter === 'inactive' && types && types.length > 0
              ? <p>No inactive CI types.</p>
              : <>
                  <p>No CI types defined yet.</p>
                  {isAdmin && <p>Click "+ New CI Type" to create your first type (e.g. Server, Network Device, Application).</p>}
                </>}
        </div>
      )}
    </div>
  )
}
