/**
 * D3: Data Dictionary — browsable list of all canonical field definitions
 * with type, options, owner, usage counts, linked forms/types.
 */
import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = '/api'

interface FieldDef {
  id: number
  key: string
  label: string
  field_type: string
  options: any[]
  validation_rules: Record<string, any>
  help_text: string
  description: string
  owner_user_id: number | null
  tags: string[]
  is_active: boolean
  is_deprecated: boolean
  usage_count: number
  linked_forms: number[]
  linked_ci_types: number[]
}

export const FieldDictionary: React.FC = () => {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const { data, isLoading } = useQuery({
    queryKey: ['field-dictionary', search, typeFilter],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const params: any = {}
      if (search) params.search = search
      if (typeFilter !== 'all') params.field_type = typeFilter
      const response = await axios.get(`${API_URL}/field-library/`, {
        headers: { Authorization: `Bearer ${token}` },
        params
      })
      const d = response.data as any
      return (d.items || d) as FieldDef[]
    }
  })

  const fields = data || []

  const fieldTypeColors: Record<string, string> = {
    string: '#3498db',
    number: '#2ecc71',
    boolean: '#9b59b6',
    date: '#e67e22',
    datetime: '#e67e22',
    text: '#1abc9c',
    select: '#f39c12',
    email: '#3498db',
    url: '#3498db',
    currency: '#2ecc71',
    relationship: '#9b59b6'
  }

  return (
    <div style={{ padding: '1.5rem' }}>
      <h2 style={{ marginBottom: '1rem' }}>Data Dictionary</h2>
      <p style={{ color: '#666', marginBottom: '1.5rem' }}>
        Canonical field definitions shared across forms and CI types.
        {fields.length > 0 && ` Showing ${fields.length} field(s).`}
      </p>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search fields..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: '0.5rem', width: '300px' }}
        />
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ padding: '0.5rem' }}>
          <option value="all">All Types</option>
          <option value="string">String</option>
          <option value="number">Number</option>
          <option value="select">Select</option>
          <option value="boolean">Boolean</option>
          <option value="date">Date</option>
          <option value="text">Text</option>
        </select>
      </div>

      {isLoading ? (
        <div>Loading...</div>
      ) : fields.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#666' }}>
          No field definitions yet. Create some in <a href="/admin/fields">Field Manager</a>.
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '1rem' }}>
          {fields.map((field) => (
            <div key={field.id} style={{
              border: '1px solid #ddd',
              borderRadius: '8px',
              padding: '1rem',
              backgroundColor: field.is_deprecated ? '#f9f9f9' : 'white'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <div>
                  <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {field.label}
                    <span style={{
                      fontSize: '0.75rem',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      backgroundColor: fieldTypeColors[field.field_type] || '#95a5a6',
                      color: 'white'
                    }}>
                      {field.field_type}
                    </span>
                    {field.is_deprecated && (
                      <span style={{ fontSize: '0.75rem', color: '#e74c3c' }}>[Deprecated]</span>
                    )}
                  </h3>
                  <div style={{ fontSize: '0.85rem', color: '#666' }}>
                    Key: <code>{field.key}</code>
                    {field.tags && field.tags.length > 0 && (
                      <span style={{ marginLeft: '1rem' }}>
                        Tags: {field.tags.map(t => <span key={t} style={{ marginRight: '0.5rem', padding: '0.1rem 0.4rem', backgroundColor: '#ecf0f1', borderRadius: '3px' }}>{t}</span>)}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {field.description && (
                <p style={{ margin: '0.5rem 0', color: '#555' }}>{field.description}</p>
              )}

              {field.help_text && (
                <p style={{ margin: '0.5rem 0', fontSize: '0.9rem', color: '#666', fontStyle: 'italic' }}>
                  ℹ️ {field.help_text}
                </p>
              )}

              {field.options && field.options.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  <strong style={{ fontSize: '0.85rem' }}>Options:</strong>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                    {field.options.map((opt: any, i: number) => (
                      <span key={i} style={{
                        padding: '0.2rem 0.5rem',
                        backgroundColor: '#ecf0f1',
                        borderRadius: '4px',
                        fontSize: '0.85rem'
                      }}>
                        {typeof opt === 'string' ? opt : opt.label || opt.value || JSON.stringify(opt)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: '#666' }}>
                Usage: {field.usage_count || 0} reference(s)
                {field.linked_forms && field.linked_forms.length > 0 && (
                  <span> · Forms: {field.linked_forms.join(', ')}</span>
                )}
                {field.linked_ci_types && field.linked_ci_types.length > 0 && (
                  <span> · CI Types: {field.linked_ci_types.join(', ')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
