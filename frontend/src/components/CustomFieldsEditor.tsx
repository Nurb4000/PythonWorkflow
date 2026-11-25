import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dataFieldApi } from '../services/api'

interface CustomFieldDef {
  id: number
  field_key: string
  label: string
  field_type: string
  config: any
  is_required: boolean
}

interface CustomFieldsEditorProps {
  targetTable: string
  existingData?: Record<string, any>
  onChange: (data: Record<string, any>) => void
  disabled?: boolean
}

export const CustomFieldsEditor: React.FC<CustomFieldsEditorProps> = ({
  targetTable,
  existingData = {},
  onChange,
  disabled = false
}) => {
  const [values, setValues] = useState<Record<string, any>>({})

  const { data: fields } = useQuery({
    queryKey: ['custom-fields', targetTable],
    queryFn: async () => {
      const res = await dataFieldApi.list({ target_table: targetTable, is_active: true })
      return res.data as CustomFieldDef[]
    }
  })

  useEffect(() => {
    const merged: Record<string, any> = {}
    fields?.forEach(f => {
      merged[f.field_key] = existingData[f.field_key] ?? ''
    })
    setValues(merged)
  }, [fields, existingData])

  const handleChange = (fieldKey: string, value: any) => {
    const updated = { ...values, [fieldKey]: value }
    setValues(updated)
    onChange(updated)
  }

  const renderFieldInput = (field: CustomFieldDef) => {
    const val = values[field.field_key] ?? ''

    if (field.field_type === 'boolean') {
      return (
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <input
            type="checkbox"
            checked={!!val}
            onChange={(e) => handleChange(field.field_key, e.target.checked)}
            disabled={disabled}
          />
          {field.label}
          {field.is_required && <span style={{ color: '#e74c3c' }}>*</span>}
        </label>
      )
    }

    if (field.field_type === 'select') {
      const options = field.config?.options || []
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <select
            className="form-select"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          >
            <option value="">-- Select --</option>
            {options.map((opt: any, i: number) => (
              <option key={i} value={opt.value}>
                {opt.label || opt.value}
              </option>
            ))}
          </select>
        </div>
      )
    }

    if (field.field_type === 'date') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <input
            type="date"
            className="form-input"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          />
        </div>
      )
    }

    if (field.field_type === 'datetime') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <input
            type="datetime-local"
            className="form-input"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          />
        </div>
      )
    }

    if (field.field_type === 'number' || field.field_type === 'currency') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <input
            type="number"
            className="form-input"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          />
        </div>
      )
    }

    if (field.field_type === 'email') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <input
            type="email"
            className="form-input"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          />
        </div>
      )
    }

    if (field.field_type === 'url') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <input
            type="url"
            className="form-input"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            disabled={disabled}
          />
        </div>
      )
    }

    if (field.field_type === 'text') {
      return (
        <div className="form-group">
          <label className="form-label">
            {field.label}
            {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
          </label>
          <textarea
            className="form-textarea"
            value={val}
            onChange={(e) => handleChange(field.field_key, e.target.value)}
            rows={3}
            disabled={disabled}
          />
        </div>
      )
    }

    // Default: string
    return (
      <div className="form-group">
        <label className="form-label">
          {field.label}
          {field.is_required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
        </label>
        <input
          type="text"
          className="form-input"
          value={val}
          onChange={(e) => handleChange(field.field_key, e.target.value)}
          disabled={disabled}
        />
      </div>
    )
  }

  if (!fields || fields.length === 0) {
    return null
  }

  return (
    <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '2px solid #eee' }}>
      <h4 style={{ marginBottom: '1rem', color: '#2c3e50' }}>Custom Fields</h4>
      <div className="grid grid-2">
        {fields.map(field => (
          <React.Fragment key={field.id}>
            {renderFieldInput(field)}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}
