import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { servicesApi, portalApi, priorityApi } from '../services/api'
import { FormRenderer } from '../components/FormRenderer'
import { useAuth } from '../components/Auth'

interface CatalogService {
  id: number
  name: string
  key: string
  description: string
  icon: string
  category_id: number | null
  owner_id: number | null
  support_group_id: number | null
  is_active: boolean
  sort_order: number
  workflow_count: number
  owner?: { id: number; username: string; full_name: string }
  support_group?: { id: number; name: string }
  category?: { id: number; name: string; key: string; icon: string }
}

interface ServiceDetail extends CatalogService {
  workflows: CatalogWorkflow[]
  custom_data: Record<string, any>
}

interface CatalogWorkflow {
  id: number
  name: string
  description: string
  portal_icon: string
  steps_count: number
  runs_count: number
  entry_form_id?: number | null
}

export const ServiceCatalog: React.FC = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [services, setServices] = useState<CatalogService[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')

  // Detail view state
  const [detail, setDetail] = useState<ServiceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Workflow launch state
  const [running, setRunning] = useState<number | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [entryFormWorkflow, setEntryFormWorkflow] = useState<CatalogWorkflow | null>(null)

  // Priority selection (Phase 3)
  const [priorityLevels, setPriorityLevels] = useState<any[]>([])
  const [selectedPriority, setSelectedPriority] = useState<number | null>(null)
  const [showPriorityModal, setShowPriorityModal] = useState<CatalogWorkflow | null>(null)

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const loadServices = useCallback(async () => {
    try {
      const res = await servicesApi.listServices()
      setServices(res.data as CatalogService[])
    } catch (error) {
      console.error('Failed to load services:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadServices()
  }, [loadServices])

  // Load priority matrix (Phase 3)
  useEffect(() => {
    priorityApi.getPortalMatrix().then(res => {
      setPriorityLevels(res.data.levels || [])
    }).catch(() => {})
  }, [])

  const loadServiceDetail = async (serviceId: number) => {
    setDetailLoading(true)
    try {
      const res = await servicesApi.getService(serviceId)
      setDetail(res.data as ServiceDetail)
    } catch (error) {
      console.error('Failed to load service detail:', error)
      setToast('Failed to load service details')
    } finally {
      setDetailLoading(false)
    }
  }

  const selectService = (svc: CatalogService) => {
    setSearchTerm('')
    setSelectedCategory('all')
    loadServiceDetail(svc.id)
  }

  const backToCatalog = () => {
    setDetail(null)
  }

  const runWorkflow = async (wf: CatalogWorkflow, priority?: number | null) => {
    if (wf.entry_form_id) {
      setEntryFormWorkflow(wf)
      return
    }

    setRunning(wf.id)
    try {
      const response = await portalApi.runWorkflow(wf.id, {}, priority)
      setToast(`Started "${wf.name}" (run #${response.data.run_id})`)
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    } finally {
      setRunning(null)
    }
  }

  const initiateWorkflow = (wf: CatalogWorkflow) => {
    const hasSla = detail && detail.custom_data?.sla_targets && priorityLevels.length > 0
    if (hasSla) {
      setSelectedPriority(null)
      setShowPriorityModal(wf)
    } else {
      runWorkflow(wf)
    }
  }

  const submitEntryForm = async (data: Record<string, any>) => {
    if (!entryFormWorkflow) return
    try {
      const response = await portalApi.runWorkflow(entryFormWorkflow.id, data)
      setToast(`Started "${entryFormWorkflow.name}" (run #${response.data.run_id})`)
      setEntryFormWorkflow(null)
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    }
  }

  const submitEntryForm = async (data: Record<string, any>) => {
    if (!entryFormWorkflow) return
    try {
      const response = await portalApi.runWorkflow(entryFormWorkflow.id, data)
      setToast(`Started "${entryFormWorkflow.name}" (run #${response.data.run_id})`)
      setEntryFormWorkflow(null)
    } catch (error: any) {
      setToast(error?.response?.data?.detail || 'Failed to start workflow')
    }
  }

  // Derive categories from services
  const categories = useMemo(() => {
    const catMap = new Map<string, { label: string; icon: string }>()
    catMap.set('all', { label: 'All', icon: '' })
    services.forEach(svc => {
      if (svc.category) {
        catMap.set(svc.category.key, { label: svc.category.name, icon: svc.category.icon })
      }
    })
    // Uncategorized
    const hasUncategorized = services.some(s => !s.category_id)
    if (hasUncategorized) {
      catMap.set('uncategorized', { label: 'General', icon: '📋' })
    }
    return Array.from(catMap.entries())
  }, [services])

  const filteredServices = useMemo(() => {
    let result = services
    if (selectedCategory !== 'all') {
      if (selectedCategory === 'uncategorized') {
        result = result.filter(s => !s.category_id)
      } else {
        result = result.filter(s => s.category?.key === selectedCategory)
      }
    }
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase()
      result = result.filter(s =>
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q) ||
        s.key.toLowerCase().includes(q)
      )
    }
    return result
  }, [services, selectedCategory, searchTerm])

  // Group by category for display
  const groupedServices = useMemo(() => {
    const groups: Record<string, CatalogService[]> = {}
    filteredServices.forEach(svc => {
      const catKey = svc.category?.key || 'uncategorized'
      if (!groups[catKey]) groups[catKey] = []
      groups[catKey].push(svc)
    })
    return groups
  }, [filteredServices])

  if (loading) {
    return <div className="loading">Loading service catalog...</div>
  }

  // ==================== DETAIL VIEW ====================
  if (detail) {
    return (
      <div>
        {toast && (
          <div className="toast" style={{
            position: 'fixed', top: '1rem', right: '1rem', zIndex: 100,
            background: '#2c3e50', color: 'white', padding: '0.75rem 1.25rem',
            borderRadius: '6px', boxShadow: '0 2px 10px rgba(0,0,0,0.25)'
          }}>
            {toast}
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

        {/* Priority selection modal (Phase 3) */}
        {showPriorityModal && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 1000
          }} onClick={() => setShowPriorityModal(null)}>
            <div className="card" style={{ maxWidth: '420px', width: '94%' }} onClick={e => e.stopPropagation()}>
              <h3 className="card-title">Select Priority</h3>
              <p style={{ fontSize: '0.9rem', opacity: 0.7, marginBottom: '1rem' }}>
                For "{showPriorityModal.name}"
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {priorityLevels.map((lvl: any) => (
                  <button
                    key={lvl.id}
                    className="btn"
                    style={{
                      justifyContent: 'flex-start',
                      borderLeft: `4px solid ${lvl.color || '#3498db'}`,
                      backgroundColor: selectedPriority === lvl.id ? '#e8f4fd' : 'transparent',
                      textAlign: 'left',
                      padding: '0.75rem 1rem',
                    }}
                    onClick={() => setSelectedPriority(lvl.id)}
                  >
                    <span style={{
                      display: 'inline-block', width: '12px', height: '12px',
                      borderRadius: '50%', backgroundColor: lvl.color || '#3498db',
                      marginRight: '0.75rem'
                    }} />
                    <strong>{lvl.name}</strong>
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.25rem' }}>
                <button
                  className="btn btn-primary"
                  disabled={selectedPriority === null}
                  onClick={() => {
                    const wf = showPriorityModal
                    setShowPriorityModal(null)
                    runWorkflow(wf, selectedPriority)
                  }}
                >
                  Submit Request
                </button>
                <button className="btn btn-secondary" onClick={() => setShowPriorityModal(null)}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Detail header */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <button className="btn btn-sm btn-secondary" onClick={backToCatalog} style={{ marginBottom: '1rem' }}>
            ← Back to Catalog
          </button>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
            <span style={{ fontSize: '3rem', lineHeight: 1 }}>{detail.icon || '📋'}</span>
            <div style={{ flex: 1 }}>
              <h2 style={{ margin: 0 }}>{detail.name}</h2>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.3rem', flexWrap: 'wrap' }}>
                <span className="badge badge-success">Active</span>
                {detail.category && (
                  <span className="badge badge-info">{detail.category.icon} {detail.category.name}</span>
                )}
              </div>
              {detail.description && (
                <p style={{ margin: '0.75rem 0 0', opacity: 0.8 }}>{detail.description}</p>
              )}
              <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.5rem', fontSize: '0.85rem', opacity: 0.7 }}>
                {detail.owner && <span>Owner: {detail.owner.full_name || detail.owner.username}</span>}
                {detail.support_group && <span>Support: {detail.support_group.name}</span>}
              </div>
            </div>
          </div>
        </div>

        {/* SLA Targets display (Phase 3) */}
        {detail.custom_data?.sla_targets && priorityLevels.length > 0 && (
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 className="card-title">Response & Resolution Targets</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Response Target</th>
                  <th>Resolution Target</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  const sla = detail.custom_data.sla_targets
                  return priorityLevels.map((lvl: any) => (
                    <tr key={lvl.id}>
                      <td>
                        <span style={{
                          display: 'inline-block', width: '10px', height: '10px',
                          borderRadius: '50%', backgroundColor: lvl.color || '#3498db',
                          marginRight: '6px'
                        }} />
                        {lvl.name}
                      </td>
                      <td>{sla.response_hours?.[String(lvl.id)] ? `${sla.response_hours[String(lvl.id)]}h` : '—'}</td>
                      <td>{sla.resolution_hours?.[String(lvl.id)] ? `${sla.resolution_hours[String(lvl.id)]}h` : '—'}</td>
                    </tr>
                  ))
                })()}
              </tbody>
            </table>
          </div>
        )}

        {/* Available Workflows */}
        <div className="card">
          <h3 className="card-title">Available Requests ({detail.workflows?.length || 0})</h3>
          {detailLoading ? (
            <div className="loading">Loading...</div>
          ) : detail.workflows && detail.workflows.length > 0 ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '1rem',
              marginTop: '1rem',
            }}>
              {detail.workflows.map(wf => (
                <div
                  key={wf.id}
                  className="stat-card"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    gap: '0.6rem',
                    minHeight: '130px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
                    <span style={{ fontSize: '2rem', lineHeight: 1 }}>{wf.portal_icon || '⚙️'}</span>
                    <h3 className="card-title" style={{ margin: 0, flex: 1 }}>{wf.name}</h3>
                  </div>
                  <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9rem', flex: 1 }}>
                    {wf.description || 'No description'}
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%' }}>
                    <button
                      className="btn btn-sm btn-primary"
                      style={{ marginLeft: 'auto' }}
                      onClick={() => initiateWorkflow(wf)}
                      disabled={running !== null}
                    >
                      {running === wf.id ? 'Submitting...' : 'Submit'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
              No requests available for this service yet.
            </div>
          )}
        </div>

        {/* Related Services (same category) — Phase 4.3 */}
        {detail.category && (
          <div className="card" style={{ marginTop: '1.5rem' }}>
            <h3 className="card-title">Related Services</h3>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
              {services
                .filter(s => s.category?.key === detail.category?.key && s.id !== detail.id)
                .map(s => (
                  <button
                    key={s.id}
                    className="btn btn-sm btn-secondary"
                    onClick={() => selectService(s)}
                    style={{ textDecoration: 'none' }}
                  >
                    {s.icon || '📋'} {s.name}
                  </button>
                ))
              }
            </div>
          </div>
        )}
      </div>
    )
  }

  // ==================== CATALOG LIST VIEW ====================
  return (
    <div>
      {/* Search */}
      <div style={{ marginBottom: '1rem' }}>
        <input
          className="form-input"
          type="text"
          placeholder="Search services..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          style={{ width: '100%', boxSizing: 'border-box' }}
        />
      </div>

      {/* Category filter pills */}
      {categories.length > 1 && (
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          {categories.map(([key, cat]) => (
            <button
              key={key}
              className="btn btn-sm"
              style={{
                backgroundColor: selectedCategory === key ? '#3498db' : '#ecf0f1',
                color: selectedCategory === key ? 'white' : '#2c3e50',
                border: 'none',
              }}
              onClick={() => setSelectedCategory(key)}
            >
              {cat.icon} {cat.label}
            </button>
          ))}
        </div>
      )}

      {/* Services grouped by category */}
      {services.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', opacity: 0.7 }}>
          No services available yet.
        </div>
      ) : filteredServices.length === 0 && searchTerm.trim() ? (
        <div className="card" style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
          No services match "{searchTerm}"
        </div>
      ) : (
        Object.entries(groupedServices).map(([catKey, catServices]) => {
          const catInfo = categories.find(([k]) => k === catKey)?.[1]
          return (
            <div key={catKey} style={{ marginBottom: '2rem' }}>
              {catKey !== 'all' && catInfo && (
                <h3 style={{ marginBottom: '0.75rem', fontSize: '1.1rem', color: '#2c3e50' }}>
                  {catInfo.icon} {catInfo.label}
                </h3>
              )}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: '1rem',
              }}>
                {catServices.map(svc => (
                  <div
                    key={svc.id}
                    className="stat-card service-tile"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      gap: '0.5rem',
                      minHeight: '120px',
                      cursor: 'pointer',
                      transition: 'transform 0.15s, box-shadow 0.15s',
                    }}
                    onClick={() => selectService(svc)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
                      <span style={{ fontSize: '2rem', lineHeight: 1 }}>{svc.icon || '📋'}</span>
                      <h3 className="card-title" style={{ margin: 0, flex: 1 }}>{svc.name}</h3>
                    </div>
                    <p style={{ margin: 0, opacity: 0.75, fontSize: '0.9rem', flex: 1 }}>
                      {svc.description || 'No description'}
                    </p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%' }}>
                      <span className="badge badge-info" style={{ marginLeft: 'auto' }}>
                        {svc.workflow_count} request{svc.workflow_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
