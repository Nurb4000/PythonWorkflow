/**
 * CI Bulk Import — upload CSV/JSON and map columns to CI type fields.
 * 
 * Backend: POST /cmdb/items/bulk-import
 */
import React, { useState, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { cmdbApi } from '../services/api'

interface CIType {
  id: number
  key: string
  name: string
  field_schema: Array<{key: string; label: string; type: string; required: boolean}>
}

interface ImportResult {
  created: number
  updated: number
  errors: Array<{index: number; name?: string; error: string}>
}

export const CIBulkImport: React.FC = () => {
  const { id: typeKey } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const [selectedType, setSelectedType] = useState<CIType | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [csvContent, setCsvContent] = useState('')
  const [upsertKey, setUpsertKey] = useState('')
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<string[]>([])
  const [result, setResult] = useState<ImportResult | null>(null)

  const { data: types } = useQuery({
    queryKey: ['cmdb-types'],
    queryFn: async () => {
      const res = await cmdbApi.listTypes()
      const d = res.data as any
      return (d.items || d) as CIType[]
    },
  })

  const importMutation = useMutation({
    mutationFn: async (data: { type_key: string; records: any[]; upsert_key?: string }) => {
      return await cmdbApi.bulkImport(data)
    },
    onSuccess: (res) => {
      setResult(res.data as ImportResult)
    },
    onError: (err: any) => {
      setErrors([err.response?.data?.detail || 'Import failed'])
    },
  })

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFile = e.target.files?.[0]
    if (!uploadedFile) return
    
    setFile(uploadedFile)
    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target?.result as string
      setCsvContent(text)
      parseCsv(text)
    }
    reader.readAsText(uploadedFile)
  }

  const parseCsv = (csv: string) => {
    const lines = csv.trim().split('\n')
    if (lines.length < 2) return
    
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
    const mapping: Record<string, string> = {}
    
    // Auto-map columns by name
    if (selectedType?.field_schema) {
      for (const field of selectedType.field_schema) {
        const match = headers.find(h => 
          h.toLowerCase() === field.key.toLowerCase() ||
          h.toLowerCase() === field.label.toLowerCase()
        )
        if (match) {
          mapping[match] = field.key
        }
      }
    }
    
    setColumnMapping(mapping)
  }

  const handleUpsertKeyChange = (key: string) => {
    setUpsertKey(key)
    if (selectedType?.field_schema) {
      const field = selectedType.field_schema.find(f => f.key === key)
      if (field) {
        // Auto-add to mapping if not already there
        if (!Object.values(columnMapping).includes(key)) {
          const newMapping = { ...columnMapping }
          // Find matching CSV header
          const lines = csvContent.trim().split('\n')
          if (lines.length > 0) {
            const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
            const csvHeader = headers.find(h => h.toLowerCase() === key.toLowerCase())
            if (csvHeader) {
              newMapping[csvHeader] = key
            }
          }
          setColumnMapping(newMapping)
        }
      }
    }
  }

  const handleImport = () => {
    if (!selectedType || !csvContent) return
    
    const lines = csvContent.trim().split('\n')
    if (lines.length < 2) {
      setErrors(['CSV must have a header row and at least one data row'])
      return
    }

    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
    const records = lines.slice(1).map((line, idx) => {
      const values = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''))
      const ci_data: Record<string, string> = {}
      
      for (let i = 0; i < headers.length; i++) {
        const mappedField = columnMapping[headers[i]]
        if (mappedField) {
          ci_data[mappedField] = values[i] || ''
        }
      }
      
      return {
        name: ci_data.name || `Record ${idx + 1}`,
        ci_data
      }
    })

    importMutation.mutate({
      type_key: selectedType.key,
      records,
      upsert_key: upsertKey || undefined
    })
  }

  if (!types) return <div className="loading">Loading CI types...</div>

  return (
    <div style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>Bulk Import CI Items</h2>
        <Link to="/cmdb/items" className="btn btn-secondary">← Back to CI Items</Link>
      </div>

      {/* Step 1: Select type */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <h3 className="card-title">1. Select CI Type</h3>
        </div>
        <div style={{ padding: '1rem' }}>
          <select
            className="form-input"
            value={typeKey || ''}
            onChange={(e) => {
              const type = types.find(t => t.key === e.target.value)
              setSelectedType(type || null)
              setColumnMapping({})
              setUpsertKey('')
            }}
            style={{ maxWidth: '400px' }}
          >
            <option value="">Select a type...</option>
            {types.map(t => (
              <option key={t.id} value={t.key}>{t.name} ({t.key})</option>
            ))}
          </select>
          
          {selectedType && (
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem' }}>Fields:</h4>
              <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                {selectedType.field_schema?.map(field => (
                  <li key={field.key}>
                    {field.label} ({field.type}) {field.required && <span style={{ color: '#dc3545' }}>*</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Step 2: Upload CSV */}
      {selectedType && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3 className="card-title">2. Upload CSV</h3>
          </div>
          <div style={{ padding: '1rem' }}>
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv,.json"
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
            <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()}>
              Choose CSV File
            </button>
            
            {file && (
              <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
                <div><strong>File:</strong> {file.name}</div>
                <div><strong>Size:</strong> {(file.size / 1024).toFixed(2)} KB</div>
              </div>
            )}

            {/* Column mapping */}
            {csvContent && (
              <div style={{ marginTop: '1.5rem' }}>
                <h4>Column Mapping</h4>
                <p style={{ color: '#666', fontSize: '0.9rem' }}>
                  Map CSV columns to CI type fields. Leave unmapped columns unused.
                </p>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                  <div>
                    <label className="form-label">CSV Headers</label>
                    <select
                      className="form-input"
                      multiple
                      style={{ height: '200px' }}
                      value={Object.keys(columnMapping)}
                      onChange={(e) => {
                        const selected = Array.from(e.target.selectedOptions, opt => opt.value)
                        const newMapping = { ...columnMapping }
                        selected.forEach(header => delete newMapping[header])
                        setColumnMapping(newMapping)
                      }}
                    >
                      {csvContent.split('\n')[0]?.split(',').map((h: string, i: number) => (
                        <option key={i} value={h.trim().replace(/^"|"$/g, '')}>{h.trim()}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="form-label">CI Type Fields</label>
                    <select
                      className="form-input"
                      multiple
                      style={{ height: '200px' }}
                      value={Object.values(columnMapping)}
                    >
                      {selectedType.field_schema?.map(field => (
                        <option key={field.key} value={field.key}>{field.label} ({field.key})</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Upsert key */}
                <div style={{ marginTop: '1rem' }}>
                  <label className="form-label">Upsert Key (optional)</label>
                  <select
                    className="form-input"
                    value={upsertKey}
                    onChange={(e) => handleUpsertKeyChange(e.target.value)}
                    style={{ maxWidth: '300px' }}
                  >
                    <option value="">No upsert (create only)</option>
                    {selectedType.field_schema?.map(field => (
                      <option key={field.key} value={field.key}>{field.label} ({field.key})</option>
                    ))}
                  </select>
                  <p style={{ color: '#666', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                    If set, records with matching values will be updated instead of created.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Import */}
      {selectedType && csvContent && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3 className="card-title">3. Import</h3>
          </div>
          <div style={{ padding: '1rem' }}>
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? 'Importing...' : 'Import CI Items'}
            </button>

            {errors.length > 0 && (
              <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#f8d7da', borderRadius: '4px', color: '#721c24' }}>
                {errors.map((err, i) => <div key={i}>{err}</div>)}
              </div>
            )}

            {result && (
              <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#d4edda', borderRadius: '4px' }}>
                <h4 style={{ margin: '0 0 0.5rem' }}>Import Complete</h4>
                <div><strong>Created:</strong> {result.created}</div>
                <div><strong>Updated:</strong> {result.updated}</div>
                {result.errors.length > 0 && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <strong style={{ color: '#dc3545' }}>Errors ({result.errors.length}):</strong>
                    <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.5rem' }}>
                      {result.errors.map((err, i) => (
                        <li key={i}>Row {err.index}: {err.error}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
