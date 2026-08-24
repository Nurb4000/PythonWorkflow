import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../components/Auth'
import { dataQueryApi } from '../services/api'

const API_URL = '/api'

interface FormField {
  name: string
  type: 'string' | 'number' | 'integer' | 'boolean' | 'email' | 'textarea' | 'select' | 'info' | 'date' | 'date-time' | 'file'
  title: string
  description?: string
  required: boolean
  options?: string[]
  content?: string
  text_align?: 'left' | 'center' | 'right'
  column?: number
  data_size?: 'short' | 'medium' | 'long'
  display_size?: 'full' | 'half' | 'third' | 'quarter'
  validation?: {
    minLength?: number
    maxLength?: number
    pattern?: string
  }
  source?: 'form' | 'reference'
  ref_table?: string
  ref_column?: string
  ref_record_id?: number | string
}

const DATA_SIZES = [
  { value: 'short', label: 'Short (50 chars)', max: 50 },
  { value: 'medium', label: 'Medium (255 chars)', max: 255 },
  { value: 'long', label: 'Long (1000 chars)', max: 1000 },
]

const DISPLAY_SIZES = [
  { value: 'full', label: 'Full Width' },
  { value: 'half', label: 'Half Width' },
  { value: 'third', label: 'Third Width' },
  { value: 'quarter', label: 'Quarter Width' },
]

interface FormSchema {
  type: 'object'
  properties: Record<string, FormField>
  required: string[]
  columns?: number
}

interface Form {
  id: number
  name: string
  description: string
  schema: FormSchema
  version: number
  environment: string
  is_published: boolean
  is_active: boolean
}

const FIELD_TYPES = [
  { value: 'string', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'integer', label: 'Integer' },
  { value: 'boolean', label: 'Checkbox' },
  { value: 'email', label: 'Email' },
  { value: 'date', label: 'Date' },
  { value: 'date-time', label: 'Date & Time' },
  { value: 'textarea', label: 'Textarea' },
  { value: 'select', label: 'Select' },
  { value: 'file', label: 'File Upload' },
  { value: 'info', label: 'Info Text' },
]

export const FormDesigner: React.FC = () => {
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const [searchParams, setSearchParams] = useSearchParams()
  const [forms, setForms] = useState<Form[]>([])
  const [selectedForm, setSelectedForm] = useState<Form | null>(null)
  const showEditor = searchParams.has('editing')
  const [view, setView] = useState<'editor' | 'preview'>('editor')
  const [newForm, setNewForm] = useState({ name: '', description: '' })
  const [fields, setFields] = useState<FormField[]>([])
  const [schema, setSchema] = useState<FormSchema>({ type: 'object', properties: {}, required: [], columns: 1 })
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [showAiDialog, setShowAiDialog] = useState(false)
  const [aiDescription, setAiDescription] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  // AI field suggestions for existing form
  const [showAiSuggest, setShowAiSuggest] = useState(false)
  const [aiSuggestPrompt, setAiSuggestPrompt] = useState('')
  const [aiSuggestedFields, setAiSuggestedFields] = useState<FormField[]>([])
  const [aiSuggestLoading, setAiSuggestLoading] = useState(false)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const [formColumns, setFormColumns] = useState<1 | 2 | 3 | 4>(1)
  const [formSearch, setFormSearch] = useState('')
  const [formStatusFilter, setFormStatusFilter] = useState('active')
  const queryClient = useQueryClient()

  const { data: formsData } = useQuery({
    queryKey: ['forms', formStatusFilter],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const params: any = {}
      if (formStatusFilter === '' || formStatusFilter === 'deactivated') {
        params.include_inactive = true
      }
      const response = await axios.get(`${API_URL}/forms`, {
        params,
        headers: { Authorization: `Bearer ${token}` }
      })
      const d = response.data as any
      return (d.items || d) as Form[]
    }
  })

  useEffect(() => {
    if (formsData) {
      setForms(formsData)
    }
  }, [formsData])

  useEffect(() => {
    if (!showEditor) {
      resetEditor()
    }
  }, [showEditor])

  // Auto-load form from URL params (?editing=1&id=N or ?preview=N)
  useEffect(() => {
    const editId = searchParams.get('id')
    const previewId = searchParams.get('preview')
    if (!forms.length || !editId && !previewId) return

    const targetId = previewId ? parseInt(previewId) : editId ? parseInt(editId) : NaN
    if (isNaN(targetId)) return

    const form = forms.find(f => f.id === targetId)
    if (!form) return

    if (previewId) {
      // Preview mode: load form, show preview view
      setSelectedForm(form)
      setNewForm({ name: form.name, description: form.description })
      setSearchParams({ editing: '1', id: String(targetId) })
      const props = form.schema?.properties || {}
      const loadedFields: FormField[] = Object.entries(props).map(([key, field]) => ({
        ...field as FormField,
        name: key,
        data_size: (field as any).data_size || 'medium',
        display_size: (field as any).display_size || 'full',
        column: (field as any).column ?? 0,
        source: (field as any).source || 'form',
      }))
      setFields(loadedFields)
      setSchema(form.schema || { type: 'object', properties: {}, required: [] })
      setFormColumns((form.schema?.columns ?? 1) as 1 | 2 | 3 | 4)
      setView('preview')
    } else if (editId && showEditor) {
      // Edit mode: load form for editing
      loadFormForEdit(form)
    }
  }, [forms.length]) // Only run once after forms load

  const { data: tableSchemas } = useQuery({
    queryKey: ['data-tables'],
    queryFn: async () => {
      const res = await dataQueryApi.listTables()
      return res.data as Array<{ table: string; display_name: string; native_columns: Array<{ name: string; type: string }> }>
    }
  })

  const createFormMutation = useMutation({
    mutationFn: async (data: { name: string; description: string; schema: FormSchema }) => {
      const token = localStorage.getItem('token')
      return axios.post(`${API_URL}/forms`, null, {
        params: {
          name: data.name,
          description: data.description,
          schema: JSON.stringify(data.schema)
        },
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] })
      setSearchParams({})
      setNewForm({ name: '', description: '' })
      resetEditor()
      setError('')
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create form')
    }
  })

  const updateFormMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const token = localStorage.getItem('token')
      return axios.put(`${API_URL}/forms/${id}`, null, {
        params: data,
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update form')
    }
  })

  const deleteFormMutation = useMutation({
    mutationFn: async (id: number) => {
      const token = localStorage.getItem('token')
      return axios.delete(`${API_URL}/forms/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to deactivate form')
    }
  })

  const resetEditor = () => {
    setFields([])
    setSchema({ type: 'object', properties: {}, required: [], columns: 1 })
    setNewForm({ name: '', description: '' })
    setSelectedForm(null)
    setView('editor')
    setFormColumns(1)
    setError('')
    setSuccessMessage('')
  }

  const loadFormForEdit = async (form: Form) => {
    setSelectedForm(form)
    setNewForm({ name: form.name, description: form.description })
    setSearchParams({ editing: '1', id: String(form.id) })
    setError('')
    setSuccessMessage('')
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/forms/${form.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      const fullForm: Form = response.data
      const props = fullForm.schema?.properties || {}
      const loadedFields: FormField[] = Object.entries(props).map(([key, field]) => ({
        ...field as FormField,
        name: key,
        data_size: (field as any).data_size || 'medium',
        display_size: (field as any).display_size || 'full',
        column: (field as any).column ?? 0,
        source: (field as any).source || 'form',
        ref_table: (field as any).ref_table || '',
        ref_column: (field as any).ref_column || ''
      }))
      setFields(loadedFields)
      setSchema(fullForm.schema || { type: 'object', properties: {}, required: [] })
      setFormColumns((fullForm.schema?.columns ?? 1) as 1 | 2 | 3 | 4)
    } catch (err: any) {
      setError('Failed to load form details: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleAiGenerate = async () => {
    if (!aiDescription.trim()) return
    setAiLoading(true)
    try {
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/ai/generate-form`, null, {
        params: { description: aiDescription },
        headers: { Authorization: `Bearer ${token}` }
      })
      const result = response.data
      if (result.success && result.schema?.properties) {
        const props = result.schema.properties as Record<string, FormField>
        const newFields: FormField[] = Object.entries(props).map(([key, field]) => ({
          ...field as FormField,
          name: key,
          data_size: (field as any).data_size || 'medium',
          display_size: (field as any).display_size || 'full',
          column: (field as any).column ?? 0
        }))
        setFields(newFields)
        setSchema(result.schema)
        setError('')
      } else {
        setError('AI returned an empty schema')
      }
      setShowAiDialog(false)
      setAiDescription('')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'AI generation failed')
    } finally {
      setAiLoading(false)
    }
  }

  const handleAiSuggestFields = async () => {
    if (!aiSuggestPrompt.trim()) return
    setAiSuggestLoading(true)
    try {
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/ai/assist-form`, {
        action: 'suggest_fields',
        description: aiSuggestPrompt,
      }, {
        headers: { Authorization: `Bearer ${token}` }
      })
      const result = response.data.result
      if (result?.fields) {
        setAiSuggestedFields(result.fields)
      } else if (result?.properties) {
        const props = result.properties as Record<string, FormField>
        const newFields: FormField[] = Object.entries(props).map(([key, field]) => ({
          ...field as FormField,
          name: key,
          data_size: (field as any).data_size || 'medium',
          display_size: (field as any).display_size || 'full',
          column: (field as any).column ?? 0,
        }))
        setAiSuggestedFields(newFields)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'AI field suggestion failed')
    } finally {
      setAiSuggestLoading(false)
    }
  }

  const handleAddField = () => {
    const newField: FormField = {
      name: `field_${fields.length + 1}`,
      type: 'string',
      title: `Field ${fields.length + 1}`,
      required: false,
      data_size: 'medium',
      display_size: 'full',
      column: 0,
      source: 'form'
    }
    setFields([...fields, newField])
  }

  const handleUpdateField = (index: number, updates: Partial<FormField>) => {
    const updated = [...fields]
    updated[index] = { ...updated[index], ...updates }
    setFields(updated)
  }

  const handleRemoveField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index))
  }

  const updateFieldOption = (index: number, optIndex: number, value: string) => {
    const updated = [...fields]
    const options = [...(updated[index].options || [])]
    options[optIndex] = value
    updated[index] = { ...updated[index], options }
    setFields(updated)
  }

  const addFieldOption = (index: number) => {
    const updated = [...fields]
    const options = [...(updated[index].options || []), `Option ${(updated[index].options || []).length + 1}`]
    updated[index] = { ...updated[index], options }
    setFields(updated)
  }

  const removeFieldOption = (index: number, optIndex: number) => {
    const updated = [...fields]
    const options = (updated[index].options || []).filter((_, oi) => oi !== optIndex)
    updated[index] = { ...updated[index], options }
    setFields(updated)
  }

  const handleMoveField = (from: number, to: number) => {
    if (to < 0 || to >= fields.length) return
    const updated = [...fields]
    const [moved] = updated.splice(from, 1)
    updated.splice(to, 0, moved)
    setFields(updated)
  }

  const handleSaveSchema = () => {
    const properties: Record<string, FormField> = {}
    const required: string[] = []
    fields.forEach(field => {
      properties[field.name] = field
      if (field.required) {
        required.push(field.name)
      }
    })
    setSchema({ type: 'object', properties, required, columns: formColumns })
  }

  const buildSchema = (): FormSchema => {
    const properties: Record<string, FormField> = {}
    const required: string[] = []
    fields.forEach(field => {
      properties[field.name] = field
      if (field.required) {
        required.push(field.name)
      }
    })
    return { type: 'object', properties, required, columns: formColumns }
  }

  const handlePublish = async () => {
    if (!selectedForm) return
    try {
      await updateFormMutation.mutateAsync({
        id: selectedForm.id,
        data: { is_published: true }
      })
      setSelectedForm({ ...selectedForm, is_published: true })
      setSuccessMessage('Form published. It is now available to users and selectable in workflows.')
      setError('')
    } catch {
      // error message handled by mutation
    }
  }

  const handleUnpublish = async () => {
    if (!selectedForm) return
    try {
      await updateFormMutation.mutateAsync({
        id: selectedForm.id,
        data: { is_published: false }
      })
      setSelectedForm({ ...selectedForm, is_published: false })
      setSuccessMessage('Form reverted to draft. It is no longer available to users.')
      setError('')
    } catch {
      // error message handled by mutation
    }
  }

  const handleSave = () => {
    const finalSchema = buildSchema()
    if (selectedForm) {
      updateFormMutation.mutate(
        { id: selectedForm.id, data: { name: newForm.name, description: newForm.description, schema: JSON.stringify(finalSchema) } },
        {
          onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['forms'] })
            setSuccessMessage('Changes saved. Click Publish to make this form available to users.')
            setError('')
          }
        }
      )
    } else {
      createFormMutation.mutate({
        name: newForm.name,
        description: newForm.description,
        schema: finalSchema
      })
    }
  }

  const renderPreview = () => {
    const renderField = (field: FormField, i: number) => (
      <div className="form-group" style={{ marginBottom: '1rem' }}>
        {field.type === 'info' ? (
          <div style={{
            textAlign: field.text_align || 'left',
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
        ) : (
          <>
        <label className="form-label">
          {field.title || field.name}
          {field.required && <span style={{ color: '#e74c3c', marginLeft: '0.25rem' }}>*</span>}
        </label>
        {field.type === 'textarea' ? (
          <textarea className="form-textarea" placeholder={field.title} rows={3} />
        ) : field.type === 'boolean' ? (
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input type="checkbox" /> {field.title}
          </label>
        ) : field.type === 'select' ? (
          <select className="form-select">
            <option value="">-- Select --</option>
            {(field.options || []).map((opt, j) => (
              <option key={j} value={opt}>{opt}</option>
            ))}
          </select>
        ) : field.type === 'number' || field.type === 'integer' ? (
          <input type="number" className="form-input" placeholder={field.title} />
        ) : field.type === 'email' ? (
          <input type="email" className="form-input" placeholder={field.title} />
        ) : field.type === 'date' ? (
          <input type="date" className="form-input" />
        ) : field.type === 'date-time' ? (
          <input type="datetime-local" className="form-input" />
        ) : field.type === 'file' ? (
          <input type="file" className="form-input" />
        ) : (
          <input type="text" className="form-input" placeholder={field.title} />
        )}
        {field.description && (
          <small style={{ color: '#666' }}>{field.description}</small>
        )}
          </>
        )}
      </div>
    )

    const getPreviewColSpan = (field: FormField) => {
      const ds = field.display_size
      if (!ds || ds === 'quarter') return 1
      if (ds === 'half') return Math.max(1, Math.floor(formColumns / 2))
      if (ds === 'third') return Math.max(1, Math.ceil(formColumns / 3))
      if (ds === 'full') return formColumns
      return 1
    }

    const renderColumnGroup = (groupFields: FormField[], startIdx: number) => {
      // Sort by column index for display order
      const sorted = [...groupFields].sort((a, b) => (a.column ?? 0) - (b.column ?? 0))
      return (
        <div key={startIdx} style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${formColumns}, 1fr)`,
          gap: '1rem',
          marginBottom: '1rem',
        }}>
          {sorted.map((f) => {
            const gi = fields.indexOf(f)
            return (
              <div key={gi} style={{ gridColumn: `span ${Math.min(getPreviewColSpan(f), formColumns)}` }}>
                {renderField(f, gi)}
              </div>
            )
          })}
        </div>
      )
    }

    const renderColumnLayout = () => {
      const groups: { fields: FormField[]; startIdx: number }[] = []
      let currentGroup: FormField[] = []
      let startIdx = 0
      fields.forEach((f, i) => {
        const isFull = f.type === 'info' || f.display_size === 'full'
        if (isFull && currentGroup.length > 0) {
          groups.push({ fields: currentGroup, startIdx })
          currentGroup = []
        }
        if (isFull) {
          groups.push({ fields: [f], startIdx: i })
        } else {
          if (currentGroup.length === 0) startIdx = i
          currentGroup.push(f)
        }
      })
      if (currentGroup.length > 0) groups.push({ fields: currentGroup, startIdx })
      return groups.map(g =>
        g.fields.length === 1 && (g.fields[0].type === 'info' || g.fields[0].display_size === 'full')
          ? <div key={g.startIdx}>{renderField(g.fields[0], g.startIdx)}</div>
          : renderColumnGroup(g.fields, g.startIdx)
      )
    }

    return (
      <div className="card">
        <h3 className="card-title">Form Preview: {newForm.name || '(unnamed)'}</h3>
        {fields.length === 0 ? (
          <p style={{ color: '#999' }}>No fields added yet</p>
        ) : formColumns === 1 ? (
          fields.map((field, i) => <div key={i}>{renderField(field, i)}</div>)
        ) : (
          renderColumnLayout()
        )}
        {fields.length > 0 && (
          <div style={{ padding: '0.5rem 0' }}>
            <button className="btn btn-primary" disabled>Submit (Preview)</button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {successMessage && <div className="success" style={{ marginBottom: '1rem' }}>{successMessage}</div>}

      {showAiDialog && (
        <div className="card" style={{ marginBottom: '1rem', border: '2px solid #9b59b6' }}>
          <h3 className="card-title">AI Form Generator</h3>
          <p style={{ color: '#666', marginBottom: '0.5rem' }}>
            Describe the form you want to create in natural language
          </p>
          <textarea
            className="form-textarea"
            value={aiDescription}
            onChange={(e) => setAiDescription(e.target.value)}
            placeholder="e.g., A contact form with name, email, phone, and a message textarea"
            rows={3}
          />
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button className="btn btn-primary" onClick={handleAiGenerate} disabled={aiLoading || !aiDescription.trim()}>
              {aiLoading ? 'Generating...' : 'Generate Fields'}
            </button>
            <button className="btn btn-secondary" onClick={() => { setShowAiDialog(false); setAiDescription('') }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="card-header">
        <h2>Form Designer</h2>
        <p style={{ color: '#7f8c8d', fontSize: '0.9rem', margin: '0.25rem 0 1rem' }}>
          Define input fields for portal entry forms. These are distinct from Custom Fields
          (admin/fields) and CMDB Type Fields (cmdb/types).
        </p>
        {canDevelop && (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-secondary" onClick={() => { setShowAiDialog(true) }}>
              AI Assist
            </button>
            <button className="btn btn-primary" onClick={() => { if (showEditor) { setSearchParams({}) } else { setSearchParams({ editing: '1' }); resetEditor() } }}>
              {showEditor ? 'Cancel' : '+ New Form'}
            </button>
          </div>
        )}
      </div>

      {showEditor && (
        <div className="card" style={{ border: selectedForm ? '3px solid #27ae60' : '3px solid #3498db' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 className="card-title" style={{ margin: 0 }}>
              {selectedForm ? `Edit Form: ${selectedForm.name}` : 'Create New Form'}
              {selectedForm && (
                <span className={`badge ${selectedForm.is_published ? 'badge-success' : 'badge-warning'}`} style={{ marginLeft: '0.75rem' }}>
                  {selectedForm.is_published ? 'Published' : 'Draft'}
                </span>
              )}
            </h3>
            <div className="btn-group" style={{ display: 'flex', gap: '0.25rem' }}>
              <button
                className={`btn btn-sm ${view === 'editor' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setView('editor')}
              >
                Editor
              </button>
              <button
                className={`btn btn-sm ${view === 'preview' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setView('preview')}
              >
                Preview
              </button>
              <span style={{ width: 1, background: '#ddd', margin: '0 0.25rem' }} />
              <button
                className={`btn btn-sm ${formColumns === 1 ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFormColumns(1)}
                title="Single column"
              >
                1 Col
              </button>
              <button
                className={`btn btn-sm ${formColumns === 2 ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFormColumns(2)}
                title="Two columns"
              >
                2 Col
              </button>
              <button
                className={`btn btn-sm ${formColumns === 3 ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFormColumns(3)}
                title="Three columns"
              >
                3 Col
              </button>
              <button
                className={`btn btn-sm ${formColumns === 4 ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFormColumns(4)}
                title="Four columns"
              >
                4 Col
              </button>
            </div>
          </div>

          {view === 'preview' ? (
            renderPreview()
          ) : (
            <>
              <div className="form-group">
                <label className="form-label">Form Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={newForm.name}
                  onChange={(e) => setNewForm({...newForm, name: e.target.value})}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea
                  className="form-textarea"
                  value={newForm.description}
                  onChange={(e) => setNewForm({...newForm, description: e.target.value})}
                />
              </div>

              <h4 style={{ marginTop: '1.5rem', marginBottom: '1rem' }}>
                Fields ({fields.length})
              </h4>

              {/* AI Suggest Fields Panel */}
              {canDevelop && (
                <div style={{ marginBottom: '1rem' }}>
                  {!showAiSuggest ? (
                    <button className="btn btn-sm btn-secondary" onClick={() => setShowAiSuggest(true)}>
                      AI Suggest Fields
                    </button>
                  ) : (
                    <div style={{ padding: '0.75rem', background: '#fef9e7', borderRadius: '6px', border: '1px solid #f9e79f' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <strong>AI Suggest Fields</strong>
                        <button className="btn btn-sm btn-secondary" onClick={() => { setShowAiSuggest(false); setAiSuggestedFields([]) }}>✕</button>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <input
                          className="form-input"
                          type="text"
                          value={aiSuggestPrompt}
                          onChange={(e) => setAiSuggestPrompt(e.target.value)}
                          placeholder="Describe fields to add..."
                          style={{ flex: 1 }}
                        />
                        <button
                          className="btn btn-warning btn-sm"
                          onClick={handleAiSuggestFields}
                          disabled={aiSuggestLoading || !aiSuggestPrompt.trim()}
                        >
                          {aiSuggestLoading ? '...' : 'Suggest'}
                        </button>
                      </div>
                      {aiSuggestedFields.length > 0 && (
                        <div>
                          <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '0.5rem' }}>Suggested fields (click + to add):</p>
                          {aiSuggestedFields.map((f, i) => (
                            <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', padding: '0.35rem 0', borderBottom: '1px solid #eee' }}>
                              <button className="btn btn-sm btn-success" onClick={() => { setFields([...fields, { ...f, name: f.name + '_' + (Date.now()) }]); setAiSuggestedFields(aiSuggestedFields.filter((_, idx) => idx !== i)) }}>+</button>
                              <span style={{ flex: 1, fontSize: '0.85rem' }}><strong>{f.title || f.name}</strong> ({f.type}){f.required ? ' *' : ''}</span>
                              {f.description && <span style={{ fontSize: '0.75rem', color: '#999' }}>{f.description}</span>}
                              <button className="btn btn-sm btn-danger" onClick={() => setAiSuggestedFields(aiSuggestedFields.filter((_, idx) => idx !== i))}>✕</button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {fields.map((field, index) => (
                <div
                    key={index}
                    className="card"
                    style={{
                      marginBottom: '0.5rem',
                      opacity: dragIndex === index ? 0.4 : 1,
                      border: field.source === 'reference' ? '2px solid #9b59b6' : (dragOverIndex === index && dragIndex !== null && dragOverIndex !== dragIndex ? '2px dashed #3498db' : '1px solid #ddd')
                    }}
                  draggable
                  onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(index)); setDragIndex(index) }}
                  onDragOver={(e) => { e.preventDefault(); setDragOverIndex(index) }}
                  onDrop={(e) => { const from = Number(e.dataTransfer.getData('text/plain')); if (!isNaN(from)) { handleMoveField(from, index) }; setDragIndex(null); setDragOverIndex(null) }}
                  onDragEnd={() => { setDragIndex(null); setDragOverIndex(null) }}
                  >
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', marginBottom: '0.5rem' }}>
                      <span style={{ cursor: 'grab', color: '#999', fontSize: '1.2rem', paddingBottom: '0.5rem' }} title="Drag to reorder">⋮⋮</span>
                      <div style={{ flex: 1 }}>
                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Field Name</label>
                        <input
                          type="text"
                          className="form-input"
                          value={field.name}
                          onChange={(e) => handleUpdateField(index, { name: e.target.value })}
                        />
                      </div>
                      <div style={{ flex: 2 }}>
                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Display Title</label>
                        <input
                          type="text"
                          className="form-input"
                          value={field.title}
                          onChange={(e) => handleUpdateField(index, { title: e.target.value })}
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <select
                        className="form-select"
                        value={field.source || 'form'}
                        onChange={(e) => handleUpdateField(index, { source: e.target.value as 'form' | 'reference', ref_table: '', ref_column: '' })}
                        style={{ flex: 1 }}
                      >
                        <option value="form">New Field</option>
                        <option value="reference">Reference Existing</option>
                      </select>
                      {field.source === 'reference' && (
                        <>
                          <select
                            className="form-select"
                            value={field.ref_table || ''}
                            onChange={(e) => handleUpdateField(index, { ref_table: e.target.value, ref_column: '' })}
                            style={{ flex: 1 }}
                          >
                            <option value="">Select Table...</option>
                            {tableSchemas?.map(t => (
                              <option key={t.table} value={t.table}>{t.display_name}</option>
                            ))}
                          </select>
                          <select
                            className="form-select"
                            value={field.ref_column || ''}
                            onChange={(e) => handleUpdateField(index, { ref_column: e.target.value })}
                            style={{ flex: 1 }}
                            disabled={!field.ref_table}
                          >
                            <option value="">Select Column...</option>
                            {field.ref_table && tableSchemas?.find(t => t.table === field.ref_table)?.native_columns.map(c => (
                              <option key={c.name} value={c.name}>{c.name} ({c.type})</option>
                            ))}
                          </select>
                          <small style={{ display: 'block', color: '#7f8c8d', fontSize: '0.7rem', marginTop: '0.25rem' }}>
                            Record ID will be resolved from workflow context at runtime
                          </small>
                        </>
                      )}
                      {field.source === 'form' && (
                        <select
                          className="form-select"
                          value={field.type}
                          onChange={(e) => handleUpdateField(index, { type: e.target.value as any })}
                          style={{ flex: 1 }}
                        >
                          {FIELD_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      )}
                    {field.type !== 'info' && (
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', whiteSpace: 'nowrap' }}>
                        <input
                          type="checkbox"
                          checked={field.required}
                          onChange={(e) => handleUpdateField(index, { required: e.target.checked })}
                          disabled={field.source === 'reference'}
                        />
                        Required
                      </label>
                    )}
                    {field.type !== 'info' && (
                      <div style={{ flex: 2 }}>
                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Description</label>
                        <input
                          type="text"
                          className="form-input"
                          value={field.description || ''}
                          onChange={(e) => handleUpdateField(index, { description: e.target.value })}
                        />
                      </div>
                    )}
                    {field.type === 'select' && (
                      <span className="badge badge-info" style={{ flex: 1, textAlign: 'center' }}>
                        {field.options?.length || 0} options
                      </span>
                    )}
                  {field.type === 'info' && (
                      <select
                        className="form-select"
                        value={field.text_align || 'left'}
                        onChange={(e) => handleUpdateField(index, { text_align: e.target.value as any })}
                        style={{ flex: 1 }}
                      >
                        <option value="left">Align Left</option>
                        <option value="center">Align Center</option>
                        <option value="right">Align Right</option>
                      </select>
                    )}
                    <select
                      className="form-select"
                      value={field.display_size || 'full'}
                      onChange={(e) => handleUpdateField(index, { display_size: e.target.value as any })}
                      style={{ flex: 1 }}
                    >
                      {DISPLAY_SIZES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                  </div>
                  {field.type === 'select' && (
                    <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: '#f8f9fa', borderRadius: '6px' }}>
                      <label className="form-label">Options</label>
                      {(field.options || []).map((opt, oi) => (
                        <div key={oi} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.35rem', alignItems: 'center' }}>
                          <input
                            type="text"
                            className="form-input"
                            value={opt}
                            onChange={(e) => updateFieldOption(index, oi, e.target.value)}
                            style={{ flex: 1 }}
                          />
                          <button type="button" className="btn btn-sm btn-danger" onClick={() => removeFieldOption(index, oi)} title="Remove option">✕</button>
                        </div>
                      ))}
                      <button type="button" className="btn btn-sm btn-secondary" onClick={() => addFieldOption(index)}>
                        + Add Option
                      </button>
                    </div>
                  )}
                  {field.type === 'info' && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <textarea
                        className="form-textarea"
                        placeholder="Enter your informational text here..."
                        value={field.content || ''}
                        onChange={(e) => handleUpdateField(index, { content: e.target.value })}
                        rows={3}
                        style={{ width: '100%', boxSizing: 'border-box' }}
                      />
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.25rem' }}>
                    {field.type !== 'info' && (
                      <select
                        className="form-select"
                        value={field.data_size || 'medium'}
                        onChange={(e) => handleUpdateField(index, { data_size: e.target.value as any })}
                        style={{ flex: 1 }}
                      >
                        {DATA_SIZES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    )}
                    {field.type !== 'info' && formColumns > 1 && (
                      <select
                        className="form-select"
                        value={field.column ?? 0}
                        onChange={(e) => handleUpdateField(index, { column: Number(e.target.value) })}
                        style={{ flex: 1 }}
                      >
                        {Array.from({ length: formColumns }, (_, i) => (
                          <option key={i} value={i}>Column {i + 1}</option>
                        ))}
                      </select>
                    )}
                    {field.type !== 'info' && <div style={{ flex: formColumns > 1 ? 0 : 1 }} />}
                    <button className="btn btn-sm btn-danger" onClick={() => handleRemoveField(index)}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                <button className="btn btn-secondary" onClick={handleAddField}>
                  + Add Field
                </button>
                <button className="btn btn-primary" onClick={handleSaveSchema}>
                  Save Schema
                </button>
              </div>
            </>
          )}

          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
            <button className="btn btn-success" onClick={handleSave} disabled={!newForm.name}>
              {selectedForm ? 'Save Changes' : 'Create Form'}
            </button>
            {selectedForm && (
              <button
                className={`btn ${selectedForm.is_published ? 'btn-warning' : 'btn-success'}`}
                onClick={selectedForm.is_published ? handleUnpublish : handlePublish}
              >
                {selectedForm.is_published ? 'Unpublish' : 'Publish'}
              </button>
            )}
          </div>
          {selectedForm && (
            <small style={{ color: '#666', display: 'block', marginTop: '0.5rem' }}>
              Save stores your draft changes. Publish makes the form available to users and selectable in workflows.
            </small>
          )}
        </div>
      )}

      {!showEditor && (
        <>
          <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
                <label className="form-label">Search</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search forms by name or description..."
                  value={formSearch}
                  onChange={(e) => setFormSearch(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Status</label>
                <select
                  className="form-select"
                  value={formStatusFilter}
                  onChange={(e) => setFormStatusFilter(e.target.value)}
                  style={{ minWidth: '150px' }}
                >
                  <option value="active">Active</option>
                  <option value="deactivated">Deactivated</option>
                  <option value="published">Published</option>
                  <option value="draft">Draft</option>
                  <option value="">All</option>
                </select>
              </div>
              {(formSearch || formStatusFilter !== 'active') && (
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => { setFormSearch(''); setFormStatusFilter('active') }}
                  style={{ marginBottom: 0 }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Description</th>
                  <th>Version</th>
                  <th>Environment</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {forms
                  .filter(form => {
                    if (formStatusFilter === 'active' && !form.is_active) return false
                    if (formStatusFilter === 'deactivated' && form.is_active) return false
                    if (formStatusFilter === 'published' && (!form.is_published || !form.is_active)) return false
                    if (formStatusFilter === 'draft' && (form.is_published || !form.is_active)) return false
                    if (formSearch) {
                      const q = formSearch.toLowerCase()
                      return form.name.toLowerCase().includes(q) || (form.description || '').toLowerCase().includes(q)
                    }
                    return true
                  })
                  .map((form) => (
                    <tr key={form.id}>
                      <td><strong>{form.name}</strong></td>
                      <td>{form.description}</td>
                      <td>v{form.version}</td>
                      <td>
                        <span className={`badge ${form.environment === 'production' ? 'badge-success' : 'badge-info'}`}>
                          {form.environment}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${form.is_published ? 'badge-success' : 'badge-warning'}`}>
                          {form.is_published ? 'Published' : 'Draft'}
                        </span>
                      </td>
                      <td>
                        {canDevelop && (
                          <>
                            <button
                              className="btn btn-sm btn-primary"
                              onClick={() => loadFormForEdit(form)}
                              style={{ marginRight: '0.5rem' }}
                            >
                              Edit
                            </button>
                            <button
                              className="btn btn-sm btn-warning"
                              onClick={() => deleteFormMutation.mutate(form.id)}
                            >
                              Deactivate
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {forms.filter(form => {
              if (formStatusFilter === 'active' && !form.is_active) return false
              if (formStatusFilter === 'deactivated' && form.is_active) return false
              if (formStatusFilter === 'published' && (!form.is_published || !form.is_active)) return false
              if (formStatusFilter === 'draft' && (form.is_published || !form.is_active)) return false
              if (formSearch) {
                const q = formSearch.toLowerCase()
                return form.name.toLowerCase().includes(q) || (form.description || '').toLowerCase().includes(q)
              }
              return true
            }).length === 0 && (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#7f8c8d' }}>
                No forms match your filters.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
