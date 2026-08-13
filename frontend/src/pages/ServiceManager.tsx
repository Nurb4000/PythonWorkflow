import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { servicesApi, authApi, kbApi } from '../services/api'
import { useAuth } from '../components/Auth'

interface ServiceItem {
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
  custom_data: Record<string, any>
  workflow_count: number
  owner?: { id: number; username: string; full_name: string }
  support_group?: { id: number; name: string }
  category?: { id: number; name: string; key: string; icon: string }
  created_at: string
  updated_at: string
}

interface CategoryItem {
  id: number
  name: string
  key: string
  icon: string
  description: string
  sort_order: number
  is_active: boolean
  service_count: number
}

export const ServiceManager: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  // Tab state: services, categories, or kb-articles
  const [activeTab, setActiveTab] = useState<'services' | 'categories' | 'kb-articles'>('services')

  // --- Services state ---
  const [svcShowForm, setSvcShowForm] = useState(false)
  const [svcEditingId, setSvcEditingId] = useState<number | null>(null)
  const [svcFormData, setSvcFormData] = useState({
    name: '',
    key: '',
    description: '',
    icon: '',
    category_id: '',
    owner_id: '',
    support_group_id: '',
    sort_order: 0,
  })
  const [svcError, setSvcError] = useState('')
  const [svcSuccess, setSvcSuccess] = useState('')
  const [svcIncludeInactive, setSvcIncludeInactive] = useState(false)

  // SLA editor state (Phase 3)
  const [slaEnabled, setSlaEnabled] = useState(false)
  const [slaResponseHours, setSlaResponseHours] = useState({ '1': '', '2': '', '3': '', '4': '' })
  const [slaResolutionHours, setSlaResolutionHours] = useState({ '1': '', '2': '', '3': '', '4': '' })

  // --- Categories state ---
  const [catShowForm, setCatShowForm] = useState(false)
  const [catEditingId, setCatEditingId] = useState<number | null>(null)
  const [catFormData, setCatFormData] = useState({
    name: '',
    key: '',
    description: '',
    icon: '',
    sort_order: 0,
  })
  const [catError, setCatError] = useState('')
  const [catSuccess, setCatSuccess] = useState('')

  // --- KB Articles state (Phase 6) ---
  interface KbArticleItem {
    id: number
    title: string
    slug: string
    content: string
    service_id: number | null
    is_published: boolean
    sort_order: number
    service?: { id: number; name: string; key: string; icon: string }
  }
  const [kbShowForm, setKbShowForm] = useState(false)
  const [kbEditingId, setKbEditingId] = useState<number | null>(null)
  const [kbFormData, setKbFormData] = useState({
    title: '',
    slug: '',
    content: '',
    service_id: '',
    sort_order: 0,
    is_published: true,
  })
  const [kbError, setKbError] = useState('')
  const [kbSuccess, setKbSuccess] = useState('')

  // --- Users & Groups for pickers ---
  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: () => authApi.listUsers().then(r => r.data as any[]),
    enabled: isAdmin && svcShowForm,
  })

  const { data: groups } = useQuery({
    queryKey: ['groups'],
    queryFn: () => authApi.listGroups().then(r => r.data as any[]),
    enabled: isAdmin && svcShowForm,
  })

  // --- Services queries/mutations ---
  const { data: services, isLoading: svcLoading } = useQuery({
    queryKey: ['services', svcIncludeInactive],
    queryFn: () =>
      servicesApi.listServices({ include_inactive: svcIncludeInactive }).then(r => r.data as ServiceItem[]),
    enabled: activeTab === 'services' || activeTab === 'kb-articles',
  })

  const svcCreateMutation = useMutation({
    mutationFn: (data: any) => servicesApi.createService(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setSvcShowForm(false)
      resetSvcForm()
      setSvcSuccess('Service created successfully')
      setTimeout(() => setSvcSuccess(''), 3000)
    },
    onError: (err: any) => {
      setSvcError(err.response?.data?.detail || 'Failed to create service')
      setTimeout(() => setSvcError(''), 5000)
    },
  })

  const svcUpdateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => servicesApi.updateService(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setSvcShowForm(false)
      setSvcEditingId(null)
      resetSvcForm()
      setSvcSuccess('Service updated successfully')
      setTimeout(() => setSvcSuccess(''), 3000)
    },
    onError: (err: any) => {
      setSvcError(err.response?.data?.detail || 'Failed to update service')
      setTimeout(() => setSvcError(''), 5000)
    },
  })

  const svcDeleteMutation = useMutation({
    mutationFn: (id: number) => servicesApi.deleteService(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setSvcSuccess('Service deactivated')
      setTimeout(() => setSvcSuccess(''), 3000)
    },
    onError: (err: any) => {
      setSvcError(err.response?.data?.detail || 'Failed to deactivate service')
      setTimeout(() => setSvcError(''), 5000)
    },
  })

  // --- Categories queries/mutations ---
  const { data: categories, isLoading: catLoading } = useQuery({
    queryKey: ['categories'],
    queryFn: () => servicesApi.listCategories().then(r => r.data as CategoryItem[]),
    enabled: activeTab === 'categories',
  })

  const catCreateMutation = useMutation({
    mutationFn: (data: any) => servicesApi.createCategory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setCatShowForm(false)
      resetCatForm()
      setCatSuccess('Category created successfully')
      setTimeout(() => setCatSuccess(''), 3000)
    },
    onError: (err: any) => {
      setCatError(err.response?.data?.detail || 'Failed to create category')
      setTimeout(() => setCatError(''), 5000)
    },
  })

  const catUpdateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => servicesApi.updateCategory(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['services'] })
      setCatShowForm(false)
      setCatEditingId(null)
      resetCatForm()
      setCatSuccess('Category updated successfully')
      setTimeout(() => setCatSuccess(''), 3000)
    },
    onError: (err: any) => {
      setCatError(err.response?.data?.detail || 'Failed to update category')
      setTimeout(() => setCatError(''), 5000)
    },
  })

  const catDeleteMutation = useMutation({
    mutationFn: (id: number) => servicesApi.deleteCategory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      setCatSuccess('Category deactivated')
      setTimeout(() => setCatSuccess(''), 3000)
    },
    onError: (err: any) => {
      setCatError(err.response?.data?.detail || 'Failed to deactivate category')
      setTimeout(() => setCatError(''), 5000)
    },
  })

  // --- KB Articles queries/mutations (Phase 6) ---
  const { data: kbArticles, isLoading: kbLoading } = useQuery({
    queryKey: ['kb-articles'],
    queryFn: () => kbApi.listArticles().then(r => r.data as KbArticleItem[]),
    enabled: activeTab === 'kb-articles',
  })

  const kbCreateMutation = useMutation({
    mutationFn: (data: any) => kbApi.createArticle(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      setKbShowForm(false)
      resetKbForm()
      setKbSuccess('Article created successfully')
      setTimeout(() => setKbSuccess(''), 3000)
    },
    onError: (err: any) => {
      setKbError(err.response?.data?.detail || 'Failed to create article')
      setTimeout(() => setKbError(''), 5000)
    },
  })

  const kbUpdateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => kbApi.updateArticle(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      setKbShowForm(false)
      setKbEditingId(null)
      resetKbForm()
      setKbSuccess('Article updated successfully')
      setTimeout(() => setKbSuccess(''), 3000)
    },
    onError: (err: any) => {
      setKbError(err.response?.data?.detail || 'Failed to update article')
      setTimeout(() => setKbError(''), 5000)
    },
  })

  const kbDeleteMutation = useMutation({
    mutationFn: (id: number) => kbApi.deleteArticle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
      setKbSuccess('Article deleted')
      setTimeout(() => setKbSuccess(''), 3000)
    },
    onError: (err: any) => {
      setKbError(err.response?.data?.detail || 'Failed to delete article')
      setTimeout(() => setKbError(''), 5000)
    },
  })

  // --- Services handlers ---
  const resetSvcForm = () => {
    setSvcFormData({ name: '', key: '', description: '', icon: '', category_id: '', owner_id: '', support_group_id: '', sort_order: 0 })
    setSlaEnabled(false)
    setSlaResponseHours({ '1': '', '2': '', '3': '', '4': '' })
    setSlaResolutionHours({ '1': '', '2': '', '3': '', '4': '' })
  }

  const handleSvcSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: any = {
      name: svcFormData.name,
      description: svcFormData.description,
      icon: svcFormData.icon,
      sort_order: svcFormData.sort_order,
    }
    if (svcFormData.key) payload.key = svcFormData.key
    if (svcFormData.category_id) payload.category_id = parseInt(svcFormData.category_id)
    if (svcFormData.owner_id) payload.owner_id = parseInt(svcFormData.owner_id)
    if (svcFormData.support_group_id) payload.support_group_id = parseInt(svcFormData.support_group_id)

    // Build custom_data with SLA targets (Phase 3)
    const customData: any = {}
    if (slaEnabled) {
      customData.sla_targets = {
        response_hours: {
          '1': slaResponseHours['1'] ? parseInt(slaResponseHours['1']) : null,
          '2': slaResponseHours['2'] ? parseInt(slaResponseHours['2']) : null,
          '3': slaResponseHours['3'] ? parseInt(slaResponseHours['3']) : null,
          '4': slaResponseHours['4'] ? parseInt(slaResponseHours['4']) : null,
        },
        resolution_hours: {
          '1': slaResolutionHours['1'] ? parseInt(slaResolutionHours['1']) : null,
          '2': slaResolutionHours['2'] ? parseInt(slaResolutionHours['2']) : null,
          '3': slaResolutionHours['3'] ? parseInt(slaResolutionHours['3']) : null,
          '4': slaResolutionHours['4'] ? parseInt(slaResolutionHours['4']) : null,
        },
      }
    }
    payload.custom_data = customData

    if (svcEditingId) {
      svcUpdateMutation.mutate({ id: svcEditingId, data: payload })
    } else {
      svcCreateMutation.mutate(payload)
    }
  }

  const editService = (svc: ServiceItem) => {
    setSvcEditingId(svc.id)
    setSvcFormData({
      name: svc.name,
      key: svc.key,
      description: svc.description,
      icon: svc.icon,
      category_id: svc.category_id?.toString() || '',
      owner_id: svc.owner_id?.toString() || '',
      support_group_id: svc.support_group_id?.toString() || '',
      sort_order: svc.sort_order,
    })
    const sla = (svc.custom_data || {}).sla_targets
    if (sla) {
      setSlaEnabled(true)
      setSlaResponseHours({
        '1': sla.response_hours?.['1'] ?? '',
        '2': sla.response_hours?.['2'] ?? '',
        '3': sla.response_hours?.['3'] ?? '',
        '4': sla.response_hours?.['4'] ?? '',
      })
      setSlaResolutionHours({
        '1': sla.resolution_hours?.['1'] ?? '',
        '2': sla.resolution_hours?.['2'] ?? '',
        '3': sla.resolution_hours?.['3'] ?? '',
        '4': sla.resolution_hours?.['4'] ?? '',
      })
    } else {
      setSlaEnabled(false)
      setSlaResponseHours({ '1': '', '2': '', '3': '', '4': '' })
      setSlaResolutionHours({ '1': '', '2': '', '3': '', '4': '' })
    }
    setSvcShowForm(true)
  }

  const toggleServiceActive = (svc: ServiceItem) => {
    if (!isAdmin) return
    const newActive = !svc.is_active
    if (newActive) {
      svcUpdateMutation.mutate({ id: svc.id, data: { is_active: true } })
    } else {
      svcDeleteMutation.mutate(svc.id)
    }
  }

  // --- Categories handlers ---
  const resetCatForm = () => {
    setCatFormData({ name: '', key: '', description: '', icon: '', sort_order: 0 })
  }

  const handleCatSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: any = {
      name: catFormData.name,
      description: catFormData.description,
      icon: catFormData.icon,
      sort_order: catFormData.sort_order,
    }
    if (catFormData.key) payload.key = catFormData.key

    if (catEditingId) {
      catUpdateMutation.mutate({ id: catEditingId, data: payload })
    } else {
      catCreateMutation.mutate(payload)
    }
  }

  const editCategory = (cat: CategoryItem) => {
    setCatEditingId(cat.id)
    setCatFormData({
      name: cat.name,
      key: cat.key,
      description: cat.description,
      icon: cat.icon,
      sort_order: cat.sort_order,
    })
    setCatShowForm(true)
  }

  const toggleCategoryActive = (cat: CategoryItem) => {
    if (!isAdmin) return
    if (!cat.is_active) {
      catUpdateMutation.mutate({ id: cat.id, data: { is_active: true } })
    } else {
      catDeleteMutation.mutate(cat.id)
    }
  }

  // --- KB Articles handlers (Phase 6) ---
  const resetKbForm = () => {
    setKbFormData({ title: '', slug: '', content: '', service_id: '', sort_order: 0, is_published: true })
  }

  const handleKbSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: any = {
      title: kbFormData.title,
      content: kbFormData.content,
      sort_order: kbFormData.sort_order,
      is_published: kbFormData.is_published,
    }
    if (kbFormData.slug) payload.slug = kbFormData.slug
    if (kbFormData.service_id) payload.service_id = parseInt(kbFormData.service_id)

    if (kbEditingId) {
      kbUpdateMutation.mutate({ id: kbEditingId, data: payload })
    } else {
      kbCreateMutation.mutate(payload)
    }
  }

  const editKbArticle = (article: KbArticleItem) => {
    setKbEditingId(article.id)
    setKbFormData({
      title: article.title,
      slug: article.slug,
      content: article.content,
      service_id: article.service_id?.toString() || '',
      sort_order: article.sort_order,
      is_published: article.is_published,
    })
    setKbShowForm(true)
  }

  // --- Render ---
  if (!isAdmin) {
    return <div className="error">Access denied. Admin role required.</div>
  }

  return (
    <div>
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <h2>Service Management</h2>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '2px solid #dee2e6' }}>
        <button
          className="btn"
          style={{
            borderBottom: activeTab === 'services' ? '2px solid #3498db' : '2px solid transparent',
            color: activeTab === 'services' ? '#3498db' : '#6c757d',
            backgroundColor: 'transparent',
            marginBottom: '-2px',
            fontWeight: activeTab === 'services' ? 700 : 400,
          }}
          onClick={() => setActiveTab('services')}
        >
          Services ({services?.length || 0})
        </button>
        <button
          className="btn"
          style={{
            borderBottom: activeTab === 'categories' ? '2px solid #3498db' : '2px solid transparent',
            color: activeTab === 'categories' ? '#3498db' : '#6c757d',
            backgroundColor: 'transparent',
            marginBottom: '-2px',
            fontWeight: activeTab === 'categories' ? 700 : 400,
          }}
          onClick={() => setActiveTab('categories')}
        >
          Categories ({categories?.length || 0})
        </button>
        <button
          className="btn"
          style={{
            borderBottom: activeTab === 'kb-articles' ? '2px solid #3498db' : '2px solid transparent',
            color: activeTab === 'kb-articles' ? '#3498db' : '#6c757d',
            backgroundColor: 'transparent',
            marginBottom: '-2px',
            fontWeight: activeTab === 'kb-articles' ? 700 : 400,
          }}
          onClick={() => setActiveTab('kb-articles')}
        >
          KB Articles ({kbArticles?.length || 0})
        </button>
      </div>

      {svcError && <div className="error">{svcError}</div>}
      {svcSuccess && <div className="success">{svcSuccess}</div>}
      {catError && <div className="error">{catError}</div>}
      {catSuccess && <div className="success">{catSuccess}</div>}
      {kbError && <div className="error">{kbError}</div>}
      {kbSuccess && <div className="success">{kbSuccess}</div>}

      {/* ==================== SERVICES TAB ==================== */}
      {activeTab === 'services' && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <button
              className="btn btn-primary"
              onClick={() => { resetSvcForm(); setSvcEditingId(null); setSvcShowForm(!svcShowForm) }}
            >
              {svcShowForm ? 'Cancel' : '+ New Service'}
            </button>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.9rem', color: '#6c757d' }}>
              <input
                type="checkbox"
                checked={svcIncludeInactive}
                onChange={e => setSvcIncludeInactive(e.target.checked)}
              />
              Show inactive
            </label>
          </div>

          {/* Service Create/Edit Form */}
          {svcShowForm && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <h3 className="card-title">{svcEditingId ? 'Edit Service' : 'New Service'}</h3>
              <form onSubmit={handleSvcSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Name *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={svcFormData.name}
                      onChange={e => setSvcFormData({ ...svcFormData, name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Key (auto-slugified if empty)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={svcFormData.key}
                      onChange={e => setSvcFormData({ ...svcFormData, key: e.target.value })}
                      placeholder="e.g. email-service"
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Icon (emoji)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={svcFormData.icon}
                      onChange={e => setSvcFormData({ ...svcFormData, icon: e.target.value })}
                      placeholder="e.g. 📧"
                      maxLength={10}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Sort Order</label>
                    <input
                      type="number"
                      className="form-input"
                      value={svcFormData.sort_order}
                      onChange={e => setSvcFormData({ ...svcFormData, sort_order: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    <select
                      className="form-select"
                      value={svcFormData.category_id}
                      onChange={e => setSvcFormData({ ...svcFormData, category_id: e.target.value })}
                    >
                      <option value="">— None —</option>
                      {(categories || []).map(cat => (
                        <option key={cat.id} value={cat.id}>{cat.icon} {cat.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Owner</label>
                    <select
                      className="form-select"
                      value={svcFormData.owner_id}
                      onChange={e => setSvcFormData({ ...svcFormData, owner_id: e.target.value })}
                    >
                      <option value="">— None —</option>
                      {(users || []).map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || u.username}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Support Group</label>
                    <select
                      className="form-select"
                      value={svcFormData.support_group_id}
                      onChange={e => setSvcFormData({ ...svcFormData, support_group_id: e.target.value })}
                    >
                      <option value="">— None —</option>
                      {(groups || []).map(g => (
                        <option key={g.id} value={g.id}>{g.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="form-group" style={{ marginTop: '1rem' }}>
                  <label className="form-label">Description</label>
                  <textarea
                    className="form-textarea"
                    value={svcFormData.description}
                    onChange={e => setSvcFormData({ ...svcFormData, description: e.target.value })}
                    rows={3}
                  />
                </div>

                {/* SLA Targets Editor (Phase 3) */}
                <div style={{ marginTop: '1.5rem', padding: '1rem', border: '1px solid #dee2e6', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <h4 style={{ margin: 0, fontSize: '1rem' }}>SLA Targets</h4>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={slaEnabled}
                        onChange={e => setSlaEnabled(e.target.checked)}
                      />
                      Enable SLA tracking
                    </label>
                  </div>
                  {slaEnabled && (
                    <div>
                      <p style={{ fontSize: '0.85rem', color: '#6c757d', margin: '0 0 0.75rem' }}>
                        Set response and resolution time targets (in hours) for each priority level. Leave blank for no target.
                      </p>
                      <table className="table" style={{ marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Priority</th>
                            <th>Response (hours)</th>
                            <th>Resolution (hours)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            { id: '1', name: 'Critical', color: '#dc3545' },
                            { id: '2', name: 'High', color: '#fd7e14' },
                            { id: '3', name: 'Medium', color: '#ffc107' },
                            { id: '4', name: 'Low', color: '#28a745' },
                          ].map((lvl: any) => (
                            <tr key={lvl.id}>
                              <td>
                                <span style={{
                                  display: 'inline-block', width: '10px', height: '10px',
                                  borderRadius: '50%', backgroundColor: lvl.color, marginRight: '6px'
                                }} />
                                {lvl.name}
                              </td>
                              <td>
                                <input
                                  type="number"
                                  className="form-input"
                                  style={{ width: '100px' }}
                                  value={slaResponseHours[lvl.id]}
                                  onChange={e => setSlaResponseHours({ ...slaResponseHours, [lvl.id]: e.target.value })}
                                  placeholder="—"
                                  min="0"
                                />
                              </td>
                              <td>
                                <input
                                  type="number"
                                  className="form-input"
                                  style={{ width: '100px' }}
                                  value={slaResolutionHours[lvl.id]}
                                  onChange={e => setSlaResolutionHours({ ...slaResolutionHours, [lvl.id]: e.target.value })}
                                  placeholder="—"
                                  min="0"
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                  <button type="submit" className="btn btn-success" disabled={svcCreateMutation.isPending || svcUpdateMutation.isPending}>
                    {svcEditingId ? 'Update Service' : 'Create Service'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => { setSvcShowForm(false); resetSvcForm(); setSvcEditingId(null) }}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Services Table */}
          <div className="card">
            <h3 className="card-title">Services ({services?.length || 0})</h3>
            {svcLoading ? <div className="loading">Loading services...</div> : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Icon</th>
                    <th>Name</th>
                    <th>Key</th>
                    <th>Category</th>
                    <th>Owner</th>
                    <th>Support Group</th>
                    <th>Workflows</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(!services || services.length === 0) && (
                    <tr><td colSpan={9} style={{ textAlign: 'center', padding: '2rem', color: '#6c757d' }}>No services yet. Create one to get started.</td></tr>
                  )}
                  {services?.map(svc => (
                    <tr key={svc.id}>
                      <td style={{ fontSize: '1.3rem' }}>{svc.icon || '📋'}</td>
                      <td><strong>{svc.name}</strong></td>
                      <td><code>{svc.key}</code></td>
                      <td>{svc.category?.name || '—'}</td>
                      <td>{svc.owner?.full_name || svc.owner?.username || '—'}</td>
                      <td>{svc.support_group?.name || '—'}</td>
                      <td><span className="badge badge-info">{svc.workflow_count}</span></td>
                      <td>
                        <span className={`badge ${svc.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {svc.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.3rem' }}>
                          <button className="btn btn-sm btn-primary" onClick={() => editService(svc)}>Edit</button>
                          <button
                            className={`btn btn-sm ${svc.is_active ? 'btn-danger' : 'btn-success'}`}
                            onClick={() => toggleServiceActive(svc)}
                          >
                            {svc.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* ==================== CATEGORIES TAB ==================== */}
      {activeTab === 'categories' && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <button
              className="btn btn-primary"
              onClick={() => { resetCatForm(); setCatEditingId(null); setCatShowForm(!catShowForm) }}
            >
              {catShowForm ? 'Cancel' : '+ New Category'}
            </button>
          </div>

          {/* Category Create/Edit Form */}
          {catShowForm && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <h3 className="card-title">{catEditingId ? 'Edit Category' : 'New Category'}</h3>
              <form onSubmit={handleCatSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Name *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={catFormData.name}
                      onChange={e => setCatFormData({ ...catFormData, name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Key (auto-slugified if empty)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={catFormData.key}
                      onChange={e => setCatFormData({ ...catFormData, key: e.target.value })}
                      placeholder="e.g. it-infrastructure"
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Icon (emoji)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={catFormData.icon}
                      onChange={e => setCatFormData({ ...catFormData, icon: e.target.value })}
                      placeholder="e.g. 🖥️"
                      maxLength={10}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Sort Order</label>
                    <input
                      type="number"
                      className="form-input"
                      value={catFormData.sort_order}
                      onChange={e => setCatFormData({ ...catFormData, sort_order: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="form-group" style={{ marginTop: '1rem' }}>
                  <label className="form-label">Description</label>
                  <textarea
                    className="form-textarea"
                    value={catFormData.description}
                    onChange={e => setCatFormData({ ...catFormData, description: e.target.value })}
                    rows={2}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                  <button type="submit" className="btn btn-success" disabled={catCreateMutation.isPending || catUpdateMutation.isPending}>
                    {catEditingId ? 'Update Category' : 'Create Category'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => { setCatShowForm(false); resetCatForm(); setCatEditingId(null) }}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Categories Table */}
          <div className="card">
            <h3 className="card-title">Categories ({categories?.length || 0})</h3>
            {catLoading ? <div className="loading">Loading categories...</div> : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Icon</th>
                    <th>Name</th>
                    <th>Key</th>
                    <th>Services</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(!categories || categories.length === 0) && (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: '#6c757d' }}>No categories yet.</td></tr>
                  )}
                  {categories?.map(cat => (
                    <tr key={cat.id}>
                      <td style={{ fontSize: '1.3rem' }}>{cat.icon || '📁'}</td>
                      <td><strong>{cat.name}</strong></td>
                      <td><code>{cat.key}</code></td>
                      <td><span className="badge badge-info">{cat.service_count}</span></td>
                      <td>
                        <span className={`badge ${cat.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {cat.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.3rem' }}>
                          <button className="btn btn-sm btn-primary" onClick={() => editCategory(cat)}>Edit</button>
                          <button
                            className={`btn btn-sm ${cat.is_active ? 'btn-danger' : 'btn-success'}`}
                            onClick={() => toggleCategoryActive(cat)}
                          >
                            {cat.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* ==================== KB ARTICLES TAB (Phase 6) ==================== */}
      {activeTab === 'kb-articles' && (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <button
              className="btn btn-primary"
              onClick={() => { resetKbForm(); setKbEditingId(null); setKbShowForm(!kbShowForm) }}
            >
              {kbShowForm ? 'Cancel' : '+ New Article'}
            </button>
          </div>

          {/* KB Article Create/Edit Form */}
          {kbShowForm && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <h3 className="card-title">{kbEditingId ? 'Edit Article' : 'New Article'}</h3>
              <form onSubmit={handleKbSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Title *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={kbFormData.title}
                      onChange={e => setKbFormData({ ...kbFormData, title: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Slug (auto-generated if empty)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={kbFormData.slug}
                      onChange={e => setKbFormData({ ...kbFormData, slug: e.target.value })}
                      placeholder="e.g. how-to-submit-request"
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Service (optional)</label>
                    <select
                      className="form-select"
                      value={kbFormData.service_id}
                      onChange={e => setKbFormData({ ...kbFormData, service_id: e.target.value })}
                    >
                      <option value="">— None —</option>
                      {(services || []).map(svc => (
                        <option key={svc.id} value={svc.id}>{svc.icon} {svc.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Sort Order</label>
                    <input
                      type="number"
                      className="form-input"
                      value={kbFormData.sort_order}
                      onChange={e => setKbFormData({ ...kbFormData, sort_order: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="form-group" style={{ marginTop: '1rem' }}>
                  <label className="form-label">Content (Markdown supported)</label>
                  <textarea
                    className="form-textarea"
                    value={kbFormData.content}
                    onChange={e => setKbFormData({ ...kbFormData, content: e.target.value })}
                    rows={8}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', alignItems: 'center' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <input
                      type="checkbox"
                      checked={kbFormData.is_published}
                      onChange={e => setKbFormData({ ...kbFormData, is_published: e.target.checked })}
                    />
                    Published
                  </label>
                  <button type="submit" className="btn btn-success" disabled={kbCreateMutation.isPending || kbUpdateMutation.isPending}>
                    {kbEditingId ? 'Update Article' : 'Create Article'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => { setKbShowForm(false); resetKbForm(); setKbEditingId(null) }}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* KB Articles Table */}
          <div className="card">
            <h3 className="card-title">Knowledge Base Articles ({kbArticles?.length || 0})</h3>
            {kbLoading ? <div className="loading">Loading articles...</div> : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Slug</th>
                    <th>Service</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(!kbArticles || kbArticles.length === 0) && (
                    <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: '#6c757d' }}>No articles yet. Create one to get started.</td></tr>
                  )}
                  {kbArticles?.map(article => (
                    <tr key={article.id}>
                      <td><strong>{article.title}</strong></td>
                      <td><code>{article.slug}</code></td>
                      <td>{article.service ? `${article.service.icon} ${article.service.name}` : '—'}</td>
                      <td>
                        <span className={`badge ${article.is_published ? 'badge-success' : 'badge-warning'}`}>
                          {article.is_published ? 'Published' : 'Draft'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.3rem' }}>
                          <button className="btn btn-sm btn-primary" onClick={() => editKbArticle(article)}>Edit</button>
                          <button className="btn btn-sm btn-danger" onClick={() => kbDeleteMutation.mutate(article.id)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
