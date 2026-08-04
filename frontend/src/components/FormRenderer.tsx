import React, { useState } from 'react'
import axios from 'axios'

const API_URL = '/api'

interface FormField {
  name: string
  type: string
  title: string
  description?: string
  required: boolean
  options?: string[]
}

interface FormSchema {
  type: string
  properties: Record<string, FormField>
  required: string[]
}

interface FormRendererProps {
  formId: number
  onSubmit?: (submissionId: number) => void
  readOnly?: boolean
}

export const FormRenderer: React.FC<FormRendererProps> = ({ formId, onSubmit, readOnly = false }) => {
  const [schema, setSchema] = useState<FormSchema | null>(null)
  const [formName, setFormName] = useState('')
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

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
      
      // Initialize form data with defaults
      const initialData: Record<string, any> = {}
      Object.keys(response.data.schema.properties).forEach(key => {
        initialData[key] = ''
      })
      setFormData(initialData)
      setLoading(false)
    } catch (err) {
      setError('Failed to load form')
      setLoading(false)
    }
  }

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
      a.download = filename
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Submission failed')
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

  return (
    <div className="card">
      <h3 className="card-title">{formName || 'Form'}</h3>
      {error && <div className="error">{error}</div>}
      
      <form onSubmit={handleSubmit}>
        {schema.properties && Object.entries(schema.properties).map(([key, field]) => (
          <div key={key} className="form-group">
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
                    ⬇ Download {formData[key]}
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
        ))}

        {!readOnly && (
          <button type="submit" className="btn btn-success" disabled={submitting}>
            {submitting ? 'Submitting...' : 'Submit'}
          </button>
        )}
      </form>
    </div>
  )
}
