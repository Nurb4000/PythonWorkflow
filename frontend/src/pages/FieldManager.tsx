import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { dataFieldApi, workflowApi, dataQueryApi } from '../services/api'

interface CustomField {
  id: number
  field_key: string
  label: string
  field_type: string
  target_table: string
  scope: string
  scope_id: number | null
  config: any
  is_required: boolean
  is_active: boolean
  created_by: number
  created_at: string
  updated_at: string
}

interface FieldFormData {
  field_key: string
  label: string
  field_type: string
  target_table: string
  scope: string
  scope_id: number | null
  config: any
  is_required: boolean
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
  { value: 'currency', label: 'Currency' },
  { value: 'relationship', label: 'Relationship (Link to another table)' },
]

const TARGET_TABLES = [
  { value: 'tasks', label: 'Tasks' },
  { value: 'workflow_runs', label: 'Workflow Runs' },
  { value: 'step_instances', label: 'Step Instances' },
  { value: 'users', label: 'Users' },
  { value: 'groups', label: 'Groups' },
  { value: 'form_submissions', label: 'Form Submissions' },
  { value: 'workflows', label: 'Workflows' },
  { value: 'workflow_steps', label: 'Workflow Steps' },
  { value: 'forms', label: 'Forms' },
  { value: 'schedules', label: 'Schedules' },
]

const emptyForm: FieldFormData = {
  field_key: '',
  label: '',
  field_type: 'string',
  target_table: 'tasks',
  scope: 'global',
  scope_id: null,
  config: {},
  is_required: false,
}

export const FieldManager: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedTable, setSelectedTable] = useState<string>('all')
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState<FieldFormData>(emptyForm)
  const [error, setError] = useState('')
  const [selectOptions, setSelectOptions] = useState<{value: string, label: string}[]>([])
  const [relTargetTable, setRelTargetTable] = useState('tasks')
  const [relTargetColumn, setRelTargetColumn] = useState('id')
  const [relDisplayColumn, setRelDisplayColumn] = useState('name')

  const { data: fields, isLoading } = useQuery({
    queryKey: ['custom-fields', selectedTable],
    queryFn: async () => {
      const params: any = {}
      if (selectedTable !== 'all') params.target_table = selectedTable
      const res = await dataFieldApi.list(params)
      return res.data as CustomField[]
    },
  })

  const { data: workflows } = useQuery({
    queryKey: ['workflows'],
    queryFn: async () => {
      const res = await workflowApi.list()
      return res.data
    },
    enabled: formData.scope === 'workflow',
  })

  // Fetch table schemas for the currently selected target table in the form
  const { data: tableSchemas } = useQuery({
    queryKey: ['data-tables'],
    queryFn: async () => {
      const res = await dataQueryApi.listTables()
      return res.data as Array<{ table: string; display_name: string; native_columns: Array<{ name: string; type: string }>; custom_fields: Array<{ field_key: string; label: string }> }>
    },
    enabled: showForm,
  })

  const currentTableSchema = tableSchemas?.find(t => t.table === formData.target_table)

  useEffect(() => {
    if (formData.field_type === 'select' && !formData.config?.options?.length) {
      setFormData(prev => ({ ...prev, config: { options: [{ value: '', label: '' }] } }))
    }
    if (formData.field_type === 'relationship' && !formData.config) {
      setFormData(prev => ({
        ...prev,
        config: { target_table: relTargetTable, target_column: relTargetColumn, display_column: relDisplayColumn },
      }))
    }
  }, [formData.field_type])

  const createMutation = useMutation({
    mutationFn: (data: FieldFormData) => dataFieldApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-fields'] })
      resetForm()
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create field')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: FieldFormData }) => dataFieldApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-fields'] })
      resetForm()
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update field')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dataFieldApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-fields'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete field')
    },
  })

  const resetForm = () => {
    setShowForm(false)
    setEditingId(null)
    setFormData(emptyForm)
    setSelectOptions([])
    setRelTargetTable('tasks')
    setRelTargetColumn('id')
    setRelDisplayColumn('name')
  }

  const startEdit = (field: CustomField) => {
    setFormData({
      field_key: field.field_key,
      label: field.label,
      field_type: field.field_type,
      target_table: field.target_table,
      scope: field.scope,
      scope_id: field.scope_id,
      config: field.config || {},
      is_required: field.is_required,
    })
    setEditingId(field.id)
    setShowForm(true)
    if (field.field_type === 'select') {
      setSelectOptions(field.config?.options || [{ value: '', label: '' }])
    }
    if (field.field_type === 'relationship') {
      setRelTargetTable(field.config?.target_table || 'tasks')
      setRelTargetColumn(field.config?.target_column || 'id')
      setRelDisplayColumn(field.config?.display_column || 'name')
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    let config = { ...formData.config }
    if (formData.field_type === 'select') {
      config.options = selectOptions.filter(o => o.value)
    } else if (formData.field_type === 'relationship') {
      config.target_table = relTargetTable
      config.target_column = relTargetColumn
      config.display_column = relDisplayColumn
    }

    const data = { ...formData, config }

    if (editingId) {
      updateMutation.mutate({ id: editingId, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const addSelectOption = () => {
    setSelectOptions([...selectOptions, { value: '', label: '' }])
  }

  const removeSelectOption = (idx: number) => {
    setSelectOptions(selectOptions.filter((_, i) => i !== idx))
  }

  const updateSelectOption = (idx: number, key: 'value' | 'label', val: string) => {
    const updated = [...selectOptions]
    updated[idx] = { ...updated[idx], [key]: val }
    setSelectOptions(updated)
  }

  const handleFieldTypeChange = (type: string) => {
    let config = {}
    if (type === 'select') config = { options: [{ value: '', label: '' }] }
    if (type === 'relationship') config = { target_table: relTargetTable, target_column: relTargetColumn, display_column: relDisplayColumn }
    setFormData({ ...formData, field_type: type, config })
  }

  const autoKey = () => {
    const key = formData.label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
    setFormData({ ...formData, field_key: key })
  }

  // Check for naming conflicts
  const nativeColumnNames = currentTableSchema?.native_columns.map(c => c.name) || []
  const customFieldKeys = currentTableSchema?.custom_fields.map(cf => cf.field_key) || []
  const hasNativeConflict = !!(formData.field_key && nativeColumnNames.includes(formData.field_key))
  const hasCustomConflict = !!(formData.field_key && !editingId && customFieldKeys.includes(formData.field_key))

  if (isLoading) return <div className="loading">Loading fields...</div>

  return (
    <div>
      <div className="card-header">
        <h2>Custom Field Manager</h2>
        <button className="btn btn-primary" onClick={() => { resetForm(); setShowForm(true); }}>
          + New Field
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="card">
        <div style={{ marginBottom: '1rem' }}>
          <label className="form-label">Filter by Table</label>
          <select
            className="form-select"
            value={selectedTable}
            onChange={(e) => setSelectedTable(e.target.value)}
            style={{ maxWidth: '300px' }}
          >
            <option value="all">All Tables</option>
            {TARGET_TABLES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        {(fields?.length || 0) === 0 ? (
          <p style={{ color: '#7f8c8d', padding: '1rem' }}>No custom fields defined yet. Click "+ New Field" to create one.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Field Key</th>
                <th>Label</th>
                <th>Type</th>
                <th>Table</th>
                <th>Scope</th>
                <th>Required</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {fields?.map((field: CustomField) => (
                <tr key={field.id}>
                  <td style={{ fontFamily: 'monospace' }}>{field.field_key}</td>
                  <td>{field.label}</td>
                  <td><span className="badge badge-info">{field.field_type}</span></td>
                  <td>{TARGET_TABLES.find(t => t.value === field.target_table)?.label || field.target_table}</td>
                  <td>
                    {field.scope === 'global' ? (
                      <span className="badge badge-success">Global</span>
                    ) : (
                      <span className="badge badge-warning">Workflow #{field.scope_id}</span>
                    )}
                  </td>
                  <td>{field.is_required ? 'Yes' : 'No'}</td>
                  <td>
                    <span className={`badge ${field.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {field.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-sm btn-primary" style={{ marginRight: '0.5rem' }} onClick={() => startEdit(field)}>
                      Edit
                    </button>
                    <button
                      className={`btn btn-sm ${field.is_active ? 'btn-warning' : 'btn-success'}`}
                      onClick={() => updateMutation.mutate({
                        id: field.id,
                        data: { is_active: !field.is_active } as any
                      })}
                    >
                      {field.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showForm && (
        <div className="card" style={{ borderTop: '3px solid #3498db' }}>
          <h3 className="card-title">{editingId ? 'Edit Field' : 'Create New Field'}</h3>
          <form onSubmit={handleSubmit}>
            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">Target Table *</label>
                <select
                  className="form-select"
                  value={formData.target_table}
                  onChange={(e) => setFormData({ ...formData, target_table: e.target.value })}
                  required
                >
                  {TARGET_TABLES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              {/* Table Schema Reference */}
              {currentTableSchema && (
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Existing Columns on "{currentTableSchema.display_name}"</label>
                  <div style={{ background: '#f8f9fa', border: '1px solid #ddd', borderRadius: '4px', padding: '0.75rem', maxHeight: '200px', overflow: 'auto' }}>
                    <div style={{ marginBottom: '0.5rem' }}>
                      <strong style={{ fontSize: '0.8rem', color: '#2c3e50' }}>Native Columns:</strong>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginTop: '0.25rem' }}>
                        {currentTableSchema.native_columns.map(c => (
                          <code key={c.name} style={{ background: '#e9ecef', padding: '0.15rem 0.4rem', borderRadius: '3px', fontSize: '0.75rem' }}>
                            {c.name}<span style={{ color: '#888' }}>: {c.type}</span>
                          </code>
                        ))}
                      </div>
                    </div>
                    {(currentTableSchema.custom_fields?.length || 0) > 0 && (
                      <div>
                        <strong style={{ fontSize: '0.8rem', color: '#2c3e50' }}>Custom Fields:</strong>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginTop: '0.25rem' }}>
                          {currentTableSchema.custom_fields.map(cf => (
                            <code key={cf.field_key} style={{ background: '#d1ecf1', padding: '0.15rem 0.4rem', borderRadius: '3px', fontSize: '0.75rem' }}>
                              {cf.field_key}<span style={{ color: '#888' }}>: {cf.label}</span>
                            </code>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <small style={{ color: '#7f8c8d' }}>Use this reference to avoid naming conflicts. Custom field keys should not duplicate native column names.</small>
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Scope *</label>
                <select
                  className="form-select"
                  value={formData.scope}
                  onChange={(e) => setFormData({ ...formData, scope: e.target.value, scope_id: null })}
                  required
                >
                  <option value="global">Global (applies to all records in table)</option>
                  <option value="workflow">Specific Workflow</option>
                </select>
              </div>

              {formData.scope === 'workflow' && (
                <div className="form-group">
                  <label className="form-label">Workflow *</label>
                  <select
                    className="form-select"
                    value={formData.scope_id || ''}
                    onChange={(e) => setFormData({ ...formData, scope_id: parseInt(e.target.value) || null })}
                    required
                  >
                    <option value="">Select a workflow...</option>
                    {(workflows || []).map((w: any) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Label *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.label}
                  onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                  placeholder="Display name for the field"
                  required
                  onBlur={autoKey}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Field Key *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.field_key}
                  onChange={(e) => setFormData({ ...formData, field_key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
                  placeholder="auto_generated_from_label"
                  required
                  style={{ fontFamily: 'monospace', borderColor: hasNativeConflict || hasCustomConflict ? '#e74c3c' : undefined }}
                />
                {hasNativeConflict && (
                  <div className="error" style={{ marginTop: '0.25rem', padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}>
                    Conflict: "{formData.field_key}" is already a native column on this table. Choose a different key.
                  </div>
                )}
                {hasCustomConflict && (
                  <div style={{ marginTop: '0.25rem', padding: '0.4rem 0.6rem', fontSize: '0.8rem', background: '#fff3cd', color: '#856404', borderRadius: '4px' }}>
                    Warning: "{formData.field_key}" already exists as a custom field on this table.
                  </div>
                )}
                {!hasNativeConflict && !hasCustomConflict && (
                  <small style={{ color: '#7f8c8d' }}>Auto-generated from label. Use lowercase letters, numbers, underscores.</small>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Field Type *</label>
                <select
                  className="form-select"
                  value={formData.field_type}
                  onChange={(e) => handleFieldTypeChange(e.target.value)}
                  required
                >
                  {FIELD_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">
                  <input type="checkbox" checked={formData.is_required} onChange={(e) => setFormData({ ...formData, is_required: e.target.checked })} />
                  {' '}Required field
                </label>
              </div>
            </div>

            {formData.field_type === 'select' && (
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Dropdown Options</label>
                {selectOptions.map((opt, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Value"
                      value={opt.value}
                      onChange={(e) => updateSelectOption(idx, 'value', e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Label"
                      value={opt.label}
                      onChange={(e) => updateSelectOption(idx, 'label', e.target.value)}
                      style={{ flex: 1 }}
                    />
                    {selectOptions.length > 1 && (
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => removeSelectOption(idx)}>X</button>
                    )}
                  </div>
                ))}
                <button type="button" className="btn btn-sm btn-secondary" onClick={addSelectOption}>+ Add Option</button>
              </div>
            )}

            {formData.field_type === 'relationship' && (
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Relationship Configuration</label>
                <div className="grid grid-3">
                  <div>
                    <small style={{ display: 'block', marginBottom: '0.25rem' }}>Target Table</small>
                    <select
                      className="form-select"
                      value={relTargetTable}
                      onChange={(e) => setRelTargetTable(e.target.value)}
                    >
                      {TARGET_TABLES.filter(t => t.value !== formData.target_table).map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <small style={{ display: 'block', marginBottom: '0.25rem' }}>Target Column (FK)</small>
                    <input
                      type="text"
                      className="form-input"
                      value={relTargetColumn}
                      onChange={(e) => setRelTargetColumn(e.target.value)}
                      placeholder="id"
                    />
                  </div>
                  <div>
                    <small style={{ display: 'block', marginBottom: '0.25rem' }}>Display Column</small>
                    <input
                      type="text"
                      className="form-input"
                      value={relDisplayColumn}
                      onChange={(e) => setRelDisplayColumn(e.target.value)}
                      placeholder="name"
                    />
                  </div>
                </div>
              </div>
            )}

            <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.5rem' }}>
              <button type="submit" className="btn btn-success" disabled={createMutation.isPending || updateMutation.isPending || hasNativeConflict}>
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : (editingId ? 'Update Field' : 'Create Field')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={resetForm}>Cancel</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
