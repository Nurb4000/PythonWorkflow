import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { workflowExportApi } from '../services/api'

interface ImportOptions {
  environment: string
  onConflict: string
  createForms: boolean
  createGroups: boolean
  matchUsersByEmail: boolean
}

export const WorkflowImportExport: React.FC = () => {
  const queryClient = useQueryClient()
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
      setImportResult(data)
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
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

  const handleDownloadDemo = async (demoFile: string) => {
    try {
      const response = await fetch(`/api/workflows/demo/${demoFile}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = demoFile
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      // Also load the demo into the import area
      const text = await blob.text()
      setFileContent(text)
      setFilename(demoFile)
    } catch (err) {
      alert('Failed to download demo: ' + err)
    }
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

      {/* Demo Workflows Section */}
      <div className="card">
        <h3 className="card-title">Demo & Training Workflows</h3>
        <p style={{ color: '#666', marginBottom: '1rem' }}>
          Click to download and automatically load a demo workflow for import. These are pre-built examples covering common patterns.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa' }}>
            <h4 style={{ marginTop: 0 }}>👋 Hello World</h4>
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>Simple linear workflow: API call → email notification.</p>
            <button className="btn btn-sm btn-primary" onClick={() => handleDownloadDemo('hello-world.xml')}>Download & Load</button>
          </div>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa' }}>
            <h4 style={{ marginTop: 0 }}>💰 Expense Approval</h4>
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>Form → approval → branching → database update + email.</p>
            <button className="btn btn-sm btn-primary" onClick={() => handleDownloadDemo('expense-approval.xml')}>Download & Load</button>
          </div>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa' }}>
            <h4 style={{ marginTop: 0 }}>📊 Data Report</h4>
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>SQL query → report node → scheduled email delivery.</p>
            <button className="btn btn-sm btn-primary" onClick={() => handleDownloadDemo('data-report.xml')}>Download & Load</button>
          </div>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa' }}>
            <h4 style={{ marginTop: 0 }}>📝 Form Collection</h4>
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>Form → human review → conditional database update.</p>
            <button className="btn btn-sm btn-primary" onClick={() => handleDownloadDemo('form-collection.xml')}>Download & Load</button>
          </div>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', background: '#fafafa' }}>
            <h4 style={{ marginTop: 0 }}>🧹 Scheduled Cleanup</h4>
            <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>Weekly cron → query old data → report → email summary.</p>
            <button className="btn btn-sm btn-primary" onClick={() => handleDownloadDemo('scheduled-cleanup.xml')}>Download & Load</button>
          </div>
        </div>
      </div>
    </div>
  )
}
