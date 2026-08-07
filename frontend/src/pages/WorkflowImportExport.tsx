import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { workflowExportApi } from '../services/api'
import { Link, useNavigate } from 'react-router-dom'

interface ImportOptions {
  environment: string
  onConflict: string
  createForms: boolean
  createGroups: boolean
  matchUsersByEmail: boolean
}

export const WorkflowImportExport: React.FC = () => {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [fileContent, setFileContent] = useState('')
  const [filename, setFilename] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)
  const [options, setOptions] = useState<ImportOptions>({
    environment: 'preserve',
    onConflict: 'copy',
    createForms: true,
    createGroups: true,
    matchUsersByEmail: true,
  })

  const importMutation = useMutation({
    mutationFn: () => workflowExportApi.import(fileContent, filename, options),
    onSuccess: (data) => {
      const result = data.data
      setImportResult(result)
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      if (result.workflowsCreatedIds && result.workflowsCreatedIds.length > 0) {
        navigate(`/workflows/${result.workflowsCreatedIds[0]}/design`)
      }
    },
    onError: (err: any) => {
      setImportResult({ errors: [err.response?.data?.detail || 'Import failed'], warnings: [] })
    }
  })

  const handleFileSelect = (file: File) => {
    if (!file.name.endsWith('.xml') && !file.name.endsWith('.json')) {
      alert('Please select an XML or JSON file')
      return
    }
    setFilename(file.name)
    const reader = new FileReader()
    reader.onload = (e) => setFileContent(e.target?.result as string)
    reader.readAsText(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  const handleImport = () => {
    if (!fileContent.trim()) return
    importMutation.mutate()
  }

  return (
    <div>
      <div className="card-header">
        <h2>Workflow Import / Export</h2>
      </div>

      {/* Import Section */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="card-title">Import Workflow</h3>

        {/* Drop Zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          style={{
            border: `2px dashed ${isDragging ? '#3498db' : '#ddd'}`,
            borderRadius: '8px',
            padding: '2rem',
            textAlign: 'center',
            background: isDragging ? '#ebf5fb' : '#fafafa',
            cursor: 'pointer',
            marginBottom: '1rem'
          }}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".xml,.json"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }}
          />
          {filename ? (
            <div>
              <p style={{ fontSize: '1.2rem', margin: 0 }}>📄 {filename}</p>
              <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>Click or drop to change file</p>
            </div>
          ) : (
            <div>
              <p style={{ fontSize: '2rem', margin: 0 }}>📁</p>
              <p style={{ color: '#7f8c8d' }}>Drop a workflow XML/JSON file here, or click to browse</p>
            </div>
          )}
        </div>

        {/* Import Options */}
        {filename && (
          <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '6px', marginBottom: '1rem' }}>
            <h4 style={{ marginTop: 0, marginBottom: '1rem' }}>Import Options</h4>
            <div className="grid grid-2">
              <div className="form-group">
                <label className="form-label">Target Environment</label>
                <select
                  className="form-select"
                  value={options.environment}
                  onChange={(e) => setOptions({ ...options, environment: e.target.value })}
                >
                  <option value="preserve">Preserve Source (from file)</option>
                  <option value="test">Force Test</option>
                  <option value="production">Force Production</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">On Name Conflict</label>
                <select
                  className="form-select"
                  value={options.onConflict}
                  onChange={(e) => setOptions({ ...options, onConflict: e.target.value })}
                >
                  <option value="copy">Create as "(Copy)"</option>
                  <option value="skip">Skip (don't import)</option>
                  <option value="overwrite">Overwrite Existing</option>
                </select>
              </div>

              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={options.createForms}
                    onChange={(e) => setOptions({ ...options, createForms: e.target.checked })}
                  />
                  Create missing forms
                </label>
              </div>

              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={options.createGroups}
                    onChange={(e) => setOptions({ ...options, createGroups: e.target.checked })}
                  />
                  Create missing groups
                </label>
              </div>

              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={options.matchUsersByEmail}
                    onChange={(e) => setOptions({ ...options, matchUsersByEmail: e.target.checked })}
                  />
                  Match users by email address
                </label>
              </div>
            </div>

            <button
              className="btn btn-success"
              style={{ marginTop: '1rem' }}
              onClick={handleImport}
              disabled={importMutation.isPending || !fileContent.trim()}
            >
              {importMutation.isPending ? 'Importing...' : 'Import Workflow'}
            </button>
          </div>
        )}

        {/* Import Result */}
        {importResult && (
          <div style={{ background: importResult.errors?.length ? '#fdf2f2' : '#f0fff4', padding: '1rem', borderRadius: '6px' }}>
            <h4 style={{ marginTop: 0 }}>Import Result</h4>
            {importResult.workflowsCreated?.length > 0 && (
              <p style={{ color: '#27ae60' }}>✓ Created: {importResult.workflowsCreated.join(', ')}</p>
            )}
            {importResult.workflowsSkipped?.length > 0 && (
              <p style={{ color: '#f39c12' }}>⊘ Skipped: {importResult.workflowsSkipped.join(', ')}</p>
            )}
            {importResult.formsCreated?.length > 0 && (
              <p style={{ color: '#27ae60' }}>✓ Forms created: {importResult.formsCreated.length}</p>
            )}
            {importResult.formsMatched?.length > 0 && (
              <p style={{ color: '#3498db' }}>↻ Forms matched: {importResult.formsMatched.join(', ')}</p>
            )}
            {importResult.groupsCreated?.length > 0 && (
              <p style={{ color: '#27ae60' }}>✓ Groups created: {importResult.groupsCreated.length}</p>
            )}
            {importResult.groupsMatched?.length > 0 && (
              <p style={{ color: '#3498db' }}>↻ Groups matched: {importResult.groupsMatched.join(', ')}</p>
            )}
            <p>Steps: {importResult.stepsCount} | Schedules: {importResult.schedulesCount}</p>
            {importResult.warnings?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ color: '#f39c12' }}>Warnings:</strong>
                <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem' }}>
                  {importResult.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}
            {importResult.errors?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ color: '#e74c3c' }}>Errors:</strong>
                <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem' }}>
                  {importResult.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Marketplace redirect note */}
      <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
        <p style={{ color: '#666', marginBottom: '1rem' }}>
          Demo workflows and reusable node templates are now available in the marketplace.
        </p>
        <Link to="/marketplace" className="btn btn-primary">
          Browse Marketplace
        </Link>
      </div>
    </div>
  )
}
