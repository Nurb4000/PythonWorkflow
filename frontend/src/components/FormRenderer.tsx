import React, { useState } from 'react'
import axios from 'axios'

const API_URL = '/api'

// Stored upload names look like `<uuid>_<original name>`; show just the original.
const originalUploadName = (storedName: string) => {
  const idx = storedName.indexOf('_')
  return idx >= 0 ? storedName.slice(idx + 1) : storedName
}

interface FormField {
  name: string
  type: string
  title: string
  description?: string
  required: boolean
  options?: string[]
  column?: number
  display_size?: string
  content?: string
  text_align?: string
}

interface FormSchema {
  type: string
  properties: Record<string, FormField>
  required: string[]
  columns?: number
}

interface FormRendererProps {
  formId: number
  onSubmit?: (submissionId: number) => void
  readOnly?: boolean
  initialData?: Record<string, any>
  onSubmitData?: (data: Record<string, any>) => void
  submitLabel?: string
}

export const FormRenderer: React.FC<FormRendererProps> = ({
  formId,
  onSubmit,
  readOnly = false,
  initialData,
  onSubmitData,
  submitLabel = 'Submit'
}) => {
  const [schema, setSchema] = useState<FormSchema | null>(null)
  const [formName, setFormName] = useState('')
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const appliedInitialRef = React.useRef<string | null>(null)

  const buildInitialData = (props: Record<string, FormField>, prefill?: Record<string, any>) => {
    const initialData: Record<string, any> = {}
    Object.keys(props).forEach(key => {
      const field = props[key]
      if (field.type === 'info') return
      const value = prefill && prefill[key] !== undefined ? prefill[key] : undefined
      if (value !== undefined) {
        initialData[key] = value
      } else if (field.type === 'boolean') {
        initialData[key] = false
      } else {
        initialData[key] = ''
      }
    })
    return initialData
  }

  React.useEffect(() => {
    loadForm()
  }, [formId])

  const loadForm = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/forms/${formId}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setSchema(response.data.schema)
      setFormName(response.data.name || '')
      setFormData(buildInitialData(response.data.schema.properties || {}, initialData))
      appliedInitialRef.current = JSON.stringify(initialData || {})
      setLoading(false)
    } catch (err) {
      setError('Failed to load form')
      setLoading(false)
    }
  }

  React.useEffect(() => {
    if (!schema) return
    const serialized = JSON.stringify(initialData || {})
    if (serialized === appliedInitialRef.current) return
    appliedInitialRef.current = serialized
    setFormData(buildInitialData(schema.properties || {}, initialData))
  }, [initialData])

  const handleInputChange = (fieldName: string, value: any) => {
    setFormData({ ...formData, [fieldName]: value })
  }

  const handleFileChange = async (fieldName: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    try {
      const token = localStorage.getItem('token')
      const fd = new FormData()
      fd.append('file', file)
      const res = await axios.post(`${API_URL}/forms/upload`, fd, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setFormData({ ...formData, [fieldName]: res.data.filename })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    }
  }

  const downloadFile = async (filename: string) => {
    try {
      const token = localStorage.getItem('token')
      const res = await axios.get(`${API_URL}/forms/download/${encodeURIComponent(filename)}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = originalUploadName(filename)
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      if (onSubmitData) {
        // Custom submit handler (e.g. complete a task with the form data)
        await onSubmitData(formData)
        setSuccess(true)
        if (onSubmit) {
          onSubmit(0)
        }
      } else {
        const token = localStorage.getItem('token')
        const response = await axios.post(
          `${API_URL}/forms/${formId}/submit`,
          formData,
          { headers: { Authorization: `Bearer ${token}` } }
        )

        setSuccess(true)
        if (onSubmit) {
          onSubmit(response.data.id)
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Submission failed')
    }
    setSubmitting(false)
  }

  if (loading) {
    return <div className="loading">Loading form...</div>
  }

  if (!schema) {
    return <div className="error">Form not found</div>
  }

  if (success) {
    return (
      <div className="card">
        <h3 className="card-title">Thank you!</h3>
        <p>Your submission has been received.</p>
      </div>
    )
  }

  const renderField = (key: string, field: FormField) => {
    if (field.type === 'info') {
      return (
        <div style={{
          textAlign: (field.text_align || 'left') as any,
          padding: '1rem',
          background: '#f8f9fa',
          borderRadius: '6px',
          border: '1px solid #e9ecef',
          color: '#495057',
          fontSize: '0.95rem',
          lineHeight: 1.6
        }}>
          {field.content || field.title || '(info text)'}
        </div>
      )
    }

    return (
      <div className="form-group">
        <label className="form-label">
          {field.title}
          {field.required && <span style={{ color: 'red' }}> *</span>}
        </label>

        {field.type === 'textarea' ? (
          <textarea
            className="form-textarea"
            value={formData[key] || ''}
            onChange={(e) => handleInputChange(key, e.target.value)}
            disabled={readOnly}
            rows={4}
          />
        ) : field.type === 'boolean' ? (
          <input
            type="checkbox"
            checked={!!formData[key]}
            onChange={(e) => handleInputChange(key, e.target.checked)}
            disabled={readOnly}
          />
        ) : field.type === 'select' && field.options ? (
          <select
            className="form-select"
            value={formData[key] || ''}
            onChange={(e) => handleInputChange(key, e.target.value)}
            disabled={readOnly}
          >
            <option value="">Select...</option>
            {field.options.map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        ) : field.type === 'date' ? (
          <input
            type="date"
            className="form-input"
            value={formData[key] || ''}
            onChange={(e) => handleInputChange(key, e.target.value)}
            disabled={readOnly}
          />
        ) : field.type === 'date-time' ? (
          <input
            type="datetime-local"
            className="form-input"
            value={formData[key] || ''}
            onChange={(e) => handleInputChange(key, e.target.value)}
            disabled={readOnly}
          />
        ) : field.type === 'file' ? (
          readOnly ? (
            formData[key] ? (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => downloadFile(formData[key])}>
                ⬇ Download {originalUploadName(formData[key])}
              </button>
            ) : (
              <small style={{ color: '#999' }}>No file uploaded</small>
            )
          ) : (
            <input
              type="file"
              className="form-input"
              onChange={(e) => handleFileChange(key, e)}
            />
          )
        ) : (
          <input
            type={field.type === 'email' ? 'email' : field.type === 'number' || field.type === 'integer' ? 'number' : 'text'}
            className="form-input"
            value={formData[key] || ''}
            onChange={(e) => handleInputChange(key, e.target.value)}
            disabled={readOnly}
            required={field.required}
          />
        )}

        {field.description && (
          <small style={{ color: '#7f8c8d' }}>{field.description}</small>
        )}
      </div>
    )
  }

  const renderFieldBlocks = (blocks: [string, FormField][]) => {
    return blocks.map(([key, field]) => (
      <div key={key} style={{ marginBottom: '1rem' }}>{renderField(key, field)}</div>
    ))
  }

  const renderColumnGroup = (group: [string, FormField][]) => {
    const cols: [string, FormField][][] = Array.from({ length: colCount }, () => [])
    group.forEach(([key, field]) => {
      const c = Math.min(field.column ?? 0, colCount - 1)
      cols[c].push([key, field])
    })
    return (
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
        {cols.map((colFields, ci) => (
          <div key={ci} style={{ flex: 1, minWidth: 0 }}>
            {colFields.map(([key, field]) => (
              <div key={key} style={{ marginBottom: '1rem' }}>{renderField(key, field)}</div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  const renderLayout = () => {
    const entries = Object.entries(schema.properties || {})
    if (colCount === 1) return renderFieldBlocks(entries)

    const groups: [string, FormField][][] = []
    let current: [string, FormField][] = []
    entries.forEach(([key, field]) => {
      const isFull = field.type === 'info' || field.display_size === 'full'
      if (isFull && current.length > 0) {
        groups.push(current)
        current = []
      }
      if (isFull) {
        groups.push([[key, field]])
      } else {
        current.push([key, field])
      }
    })
    if (current.length > 0) groups.push(current)

    return groups.map((g, gi) =>
      g.length === 1 && (g[0][1].type === 'info' || g[0][1].display_size === 'full')
        ? <div key={gi} style={{ marginBottom: '1rem' }}>{renderField(g[0][0], g[0][1])}</div>
        : <div key={gi}>{renderColumnGroup(g)}</div>
    )
  }

  const colCount = schema.columns && schema.columns > 1 ? Math.min(schema.columns, 4) : 1

  return (
    <div className="card">
      <h3 className="card-title">{formName || 'Form'}</h3>
      {error && <div className="error">{error}</div>}

      <form onSubmit={handleSubmit}>
        {renderLayout()}

        {!readOnly && (
          <button type="submit" className="btn btn-success" disabled={submitting}>
            {submitting ? 'Submitting...' : submitLabel}
          </button>
        )}
      </form>
    </div>
  )
}
