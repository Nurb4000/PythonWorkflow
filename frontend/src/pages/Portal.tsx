import React, { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { portalApi } from '../services/api'
import { FormRenderer } from '../components/FormRenderer'

interface PortalWorkflow {
  id: number
  name: string
  description: string
  environment: string
  is_published: boolean
  portal_icon: string
  portal_order: number
  portal_visible: boolean
  portal_link_url?: string
  entry_form_id?: number | null  // P3.3
}

interface PortalBanner {
  enabled: boolean
  title: string
  message: string
  color: string
}

export const Portal: React.FC = () => {
  const [workflows, setWorkflows] = useState<PortalWorkflow[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState<number | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [entryFormWorkflow, setEntryFormWorkflow] = useState<PortalWorkflow | null>(null)
  const [banner, setBanner] = useState<PortalBanner>({ enabled: false, title: '', message: '', color: '#f39c12' })
  const [searchTerm, setSearchTerm] = useState('')

  const load = useCallback(async () => {
    try {
      const [wfResponse, bannerResponse] = await Promise.all([
        portalApi.listWorkflows(),
        axios.get('/api/portal/banner')
      ])
      setWorkflows(wfResponse.data)
      if (bannerResponse.data.enabled) {
        setBanner(bannerResponse.data)
      }
    } catch (error) {
      console.error('Failed to load portal data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const runWorkflow = async (wf: PortalWorkflow) => {
    // P3.3: If workflow has an entry form, show it first
    if (wf.entry_form_id) {
      setEntryFormWorkflow(wf)
      return
    }
    
    setRunning(wf.id)
    try {
      const response = await portalApi.runWorkflow(wf.id, {})
      setToast(`Started "${wf.name}" (run #${response.data.run_id})`)
      await load()
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    } finally {
      setRunning(null)
      setEntryFormWorkflow(null)
    }
  }

  const submitEntryForm = async (data: Record<string, any>) => {
    if (!entryFormWorkflow) return
    try {
      const response = await portalApi.runWorkflow(entryFormWorkflow.id, data)
      setToast(`Started "${entryFormWorkflow.name}" (run #${response.data.run_id})`)
      await load()
      setEntryFormWorkflow(null)
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    }
  }

  const filteredWorkflows = useMemo(() => {
    if (!searchTerm.trim()) return workflows
    const q = searchTerm.toLowerCase()
    return workflows.filter(wf =>
      wf.name.toLowerCase().includes(q) ||
      (wf.description || '').toLowerCase().includes(q)
    )
  }, [workflows, searchTerm])

  if (loading) {
    return <div className="loading">Loading offerings...</div>
  }

  return (
    <div>
      {toast && (
        <div className="toast" style={{
          position: 'fixed',
          top: '1rem',
          right: '1rem',
          zIndex: 100,
          background: '#2c3e50',
          color: 'white',
          padding: '0.75rem 1.25rem',
          borderRadius: '6px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.25)'
        }}>
          {toast}
        </div>
      )}

      {banner.enabled && banner.message && (
        <div style={{
          backgroundColor: banner.color,
          color: '#fff',
          padding: '0.75rem 1rem',
          borderRadius: '6px',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem',
          boxShadow: '0 1px 4px rgba(0,0,0,0.15)'
        }}>
          <span style={{ fontSize: '1.3rem', lineHeight: 1, flexShrink: 0 }}>⚠️</span>
          <div style={{ flex: 1 }}>
            {banner.title && <strong style={{ display: 'block', marginBottom: '0.25rem' }}>{banner.title}</strong>}
            <span style={{ fontSize: '0.9rem', opacity: 0.95 }}>{banner.message}</span>
          </div>
        </div>
      )}

      {/* Entry form modal */}
      {entryFormWorkflow && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setEntryFormWorkflow(null)}>
          <div className="card" style={{ maxWidth: '900px', width: '94%', maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            {entryFormWorkflow.entry_form_id && (
              <FormRenderer
                formId={entryFormWorkflow.entry_form_id}
                submitLabel="Start Workflow"
                onSubmitData={submitEntryForm}
              />
            )}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button className="btn btn-secondary" onClick={() => setEntryFormWorkflow(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {workflows.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', opacity: 0.7 }}>
          No workflows are currently available. Check back soon.
        </div>
      ) : (
        <>
          <div style={{ marginBottom: '1rem', maxWidth: '1400px' }}>
            <input
              className="form-input"
              type="text"
              placeholder="Search workflows by name or description..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>
          {filteredWorkflows.length === 0 && searchTerm.trim() ? (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', opacity: 0.7, marginBottom: '2rem' }}>
              No workflows match "{searchTerm}"
            </div>
          ) : (
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '1rem',
              marginBottom: '2rem',
              maxWidth: '1400px'
            }}>
              {filteredWorkflows.map(wf => (
            <div
              key={wf.id}
              className="stat-card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: '0.6rem',
                minHeight: '150px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
                <span style={{ fontSize: '2.2rem', lineHeight: 1 }}>{wf.portal_icon || '⚙️'}</span>
                <h3 className="card-title" style={{ margin: 0, flex: 1 }}>{wf.name}</h3>
              </div>
              <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9rem', flex: 1 }}>
                {wf.description || 'No description provided'}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%' }}>
                {wf.portal_link_url ? (
                  <a
                    href={wf.portal_link_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-sm btn-primary"
                    style={{ marginLeft: 'auto', textDecoration: 'none' }}
                  >
                    Go To →
                  </a>
                ) : (
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ marginLeft: 'auto' }}
                    onClick={() => runWorkflow(wf)}
                    disabled={running !== null}
                  >
                    {running === wf.id ? 'Submitting...' : 'Submit'}
                  </button>
                )}
              </div>
            </div>
          ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
