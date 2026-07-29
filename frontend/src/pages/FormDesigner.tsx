import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

interface FormField {
  name: string
  type: 'string' | 'number' | 'integer' | 'boolean' | 'email' | 'textarea' | 'select'
  title: string
  description?: string
  required: boolean
  options?: string[]  // For select fields
  validation?: {
    minLength?: number
    maxLength?: number
    pattern?: string
  }
}

interface FormSchema {
  type: 'object'
  properties: Record<string, FormField>
  required: string[]
}

interface Form {
  id: number
  name: string
  description: string
  schema: FormSchema
  version: number
  environment: string
  is_published: boolean
}

export const FormDesigner: React.FC = () => {
  const [forms, setForms] = useState<Form[]>([])
  const [selectedForm, setSelectedForm] = useState<Form | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', description: '' })
  const [fields, setFields] = useState<FormField[]>([])
  const [schema, setSchema] = useState<FormSchema>({ type: 'object', properties: {}, required: [] })
  const queryClient = useQueryClient()

  const { data: formsData } = useQuery({
    queryKey: ['forms'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/forms`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data as Form[]
    }
  })

  useEffect(() => {
    if (formsData) {
      setForms(formsData)
    }
  }, [formsData])

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
      setShowEditor(false)
      setNewForm({ name: '', description: '' })
      resetEditor()
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
    }
  })

  const resetEditor = () => {
    setFields([])
    setSchema({ type: 'object', properties: {}, required: [] })
  }

  const handleAddField = () => {
    const newField: FormField = {
      name: `field_${fields.length + 1}`,
      type: 'string',
      title: `Field ${fields.length + 1}`,
      required: false
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

  const handleSaveSchema = () => {
    const properties: Record<string, FormField> = {}
    const required: string[] = []
    
    fields.forEach(field => {
      properties[field.name] = field
      if (field.required) {
        required.push(field.name)
      }
    })
    
    setSchema({ type: 'object', properties, required })
  }

  const handlePublish = async () => {
    if (selectedForm) {
      await updateFormMutation.mutateAsync({
        id: selectedForm.id,
        data: { schema: JSON.stringify(schema), is_published: true }
      })
    }
  }

  const handleCreate = () => {
    createFormMutation.mutate({
      name: newForm.name,
      description: newForm.description,
      schema
    })
  }

  return (
    <div>
      <div className="card-header">
        <h2>Form Designer</h2>
        <button className="btn btn-primary" onClick={() => setShowEditor(!showEditor)}>
          {showEditor ? 'Cancel' : '+ New Form'}
        </button>
      </div>

      {showEditor && (
        <div className="card">
          <h3 className="card-title">Create New Form</h3>
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

          <h4 style={{ marginTop: '1.5rem', marginBottom: '1rem' }}>Fields</h4>
          {fields.map((field, index) => (
            <div key={index} className="card" style={{ marginBottom: '0.5rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr 1fr', gap: '0.5rem' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Field Name"
                  value={field.name}
                  onChange={(e) => handleUpdateField(index, { name: e.target.value })}
                />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Title"
                  value={field.title}
                  onChange={(e) => handleUpdateField(index, { title: e.target.value })}
                />
                <select
                  className="form-select"
                  value={field.type}
                  onChange={(e) => handleUpdateField(index, { type: e.target.value as any })}
                >
                  <option value="string">Text</option>
                  <option value="number">Number</option>
                  <option value="integer">Integer</option>
                  <option value="boolean">Checkbox</option>
                  <option value="email">Email</option>
                  <option value="textarea">Textarea</option>
                  <option value="select">Select</option>
                </select>
                <label style={{ display: 'flex', alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={field.required}
                    onChange={(e) => handleUpdateField(index, { required: e.target.checked })}
                  />
                  Required
                </label>
                <button className="btn btn-sm btn-danger" onClick={() => handleRemoveField(index)}>
                  Remove
                </button>
              </div>
            </div>
          ))}
          
          <button className="btn btn-secondary" onClick={handleAddField} style={{ marginTop: '1rem' }}>
            + Add Field
          </button>

          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
            <button className="btn btn-success" onClick={handleSaveSchema}>
              Save Schema
            </button>
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newForm.name || !schema.properties}>
              Create Form
            </button>
          </div>
        </div>
      )}

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
            {forms.map((form) => (
              <tr key={form.id}>
                <td>
                  <strong>{form.name}</strong>
                </td>
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
                  <button 
                    className="btn btn-sm btn-primary"
                    onClick={() => { setSelectedForm(form); setShowEditor(true) }}
                    style={{ marginRight: '0.5rem' }}
                  >
                    Edit
                  </button>
                  <button 
                    className="btn btn-sm btn-danger"
                    onClick={() => deleteFormMutation.mutate(form.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
