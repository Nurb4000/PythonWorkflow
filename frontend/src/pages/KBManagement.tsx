import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { kbApi, authApi } from '../services/api'

const API_URL = '/api'

interface KbArticleItem {
  id: number
  title: string
  slug: string
  content: string
  service_id: number | null
  is_published: boolean
  is_featured: boolean
  display_order: number
  sort_order: number
  allowed_groups: Array<{id: number, name: string}>
  created_at?: string
  updated_at?: string
  service?: { id: number; name: string; key: string; icon: string }
}

interface Group {
  id: number
  name: string
  description: string
  group_type: string
  is_active: boolean
  user_count: number
  users: Array<{id: number, username: string}>
  custom_data?: Record<string, any>
}

interface ServiceItem {
  id: number
  name: string
  key: string
  icon: string
}

export const KBManagement: React.FC = () => {
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({
    title: '',
    slug: '',
    content: '',
    service_id: '',
    sort_order: 0,
    is_published: true,
    is_featured: false,
    display_order: 0,
  })
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  // Filter state
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('published')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setSearchTerm(searchInput), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchInput])

  const queryClient = useQueryClient()

  const { data: articles, isLoading, error: articlesError } = useQuery({
    queryKey: ['kb-articles-admin'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/kb-articles/admin`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data as KbArticleItem[]
    }
  })

  const { data: groups } = useQuery({
    queryKey: ['groups', false],
    queryFn: async () => {
      const response = await authApi.listGroups(false)
      return response.data as Group[]
    },
    enabled: showForm,
  })

  const { data: services } = useQuery({
    queryKey: ['services-all'],
    queryFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/services/services`, {
        params: { include_inactive: true },
        headers: { Authorization: `Bearer ${token}` }
      })
      return response.data as ServiceItem[]
    },
    enabled: showForm,
  })

  const createMutation = useMutation({
    mutationFn: (data: any) => kbApi.createArticle(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles-admin'] })
      setShowForm(false)
      resetForm()
      setSuccessMessage('Article created successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to create article')
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => kbApi.updateArticle(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles-admin'] })
      setShowForm(false)
      setEditingId(null)
      resetForm()
      setSuccessMessage('Article updated successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update article')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => kbApi.deleteArticle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kb-articles-admin'] })
      setSuccessMessage('Article unpublished')
      setTimeout(() => setSuccessMessage(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to delete article')
    }
  })

  const exportMutation = useMutation({
    mutationFn: async () => {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/kb-articles/export`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob' as 'json'
      })
      return response.data
    },
    onSuccess: (data) => {
      const url = window.URL.createObjectURL(new Blob([data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `kb_articles_${new Date().toISOString().slice(0, 10)}.json`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setSuccessMessage('Articles exported successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to export articles')
    }
  })

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const token = localStorage.getItem('token')
      const response = await axios.post(`${API_URL}/kb-articles/import`, data, {
        headers: { Authorization: `Bearer ${token}` }
      })
      queryClient.invalidateQueries({ queryKey: ['kb-articles-admin'] })
      setSuccessMessage(response.data.message || 'Articles imported successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import articles')
    }
    e.target.value = ''
  }

  const resetForm = () => {
    setFormData({ title: '', slug: '', content: '', service_id: '', sort_order: 0, is_published: true, is_featured: false, display_order: 0 })
    setSelectedGroupIds([])
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: any = {
      title: formData.title,
      content: formData.content,
      sort_order: formData.sort_order,
      is_published: formData.is_published,
      is_featured: formData.is_featured,
      display_order: formData.display_order,
    }
    if (formData.slug) payload.slug = formData.slug
    if (formData.service_id) payload.service_id = parseInt(formData.service_id)
    if (selectedGroupIds.length > 0) {
      payload.allowed_group_ids = selectedGroupIds
    }

    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const editArticle = (article: KbArticleItem) => {
    setEditingId(article.id)
    setFormData({
      title: article.title,
      slug: article.slug,
      content: article.content,
      service_id: article.service_id?.toString() || '',
      sort_order: article.sort_order,
      is_published: article.is_published,
      is_featured: article.is_featured || false,
      display_order: article.display_order || 0,
    })
    setSelectedGroupIds((article.allowed_groups || []).map(g => g.id))
    setShowForm(true)
  }

  const filteredArticles = (articles || []).filter(article => {
    if (statusFilter === 'published' && !article.is_published) return false
    if (statusFilter === 'draft' && article.is_published) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (
        article.title.toLowerCase().includes(q) ||
        article.slug.toLowerCase().includes(q) ||
        (article.content || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  if (isLoading) {
    return <div className="loading">Loading articles...</div>
  }

  if (articlesError) {
    return <div className="error">Failed to load articles: {(articlesError as Error).message}</div>
  }

  return (
    <div>
      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {successMessage && <div className="success" style={{ marginBottom: '1rem' }}>{successMessage}</div>}

      <div className="card-header">
        <h2>Knowledge Base</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to="/marketplace" className="btn btn-secondary">Marketplace</Link>
          <label className="btn btn-secondary" style={{ cursor: 'pointer' }}>
            Import
            <input
              type="file"
              accept=".json"
              onChange={handleImport}
              style={{ display: 'none' }}
            />
          </label>
          <button className="btn btn-secondary" onClick={() => exportMutation.mutate()}>Export</button>
          <button className="btn btn-primary" onClick={() => { resetForm(); setEditingId(null); setShowForm(!showForm) }}>
            {showForm ? 'Cancel' : '+ New Article'}
          </button>
        </div>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 className="card-title">{editingId ? 'Edit Article' : 'New Article'}</h3>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Title *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.title}
                  onChange={e => setFormData({ ...formData, title: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Slug (auto-generated if empty)</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.slug}
                  onChange={e => setFormData({ ...formData, slug: e.target.value })}
                  placeholder="e.g. how-to-submit-request"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Service (optional)</label>
                <select
                  className="form-select"
                  value={formData.service_id}
                  onChange={e => setFormData({ ...formData, service_id: e.target.value })}
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
                  value={formData.sort_order}
                  onChange={e => setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Display Order (Featured)</label>
                <input
                  type="number"
                  className="form-input"
                  value={formData.display_order}
                  onChange={e => setFormData({ ...formData, display_order: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">Content (Markdown supported)</label>
              <textarea
                className="form-textarea"
                value={formData.content}
                onChange={e => setFormData({ ...formData, content: e.target.value })}
                rows={8}
              />
            </div>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">Visible To Groups (empty = all users)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {(groups || []).map(g => (
                  <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                    <input
                      type="checkbox"
                      checked={selectedGroupIds.includes(g.id)}
                      onChange={() => {
                        setSelectedGroupIds(prev =>
                          prev.includes(g.id) ? prev.filter(id => id !== g.id) : [...prev, g.id]
                        )
                      }}
                    />
                    {g.name}
                  </label>
                ))}
                {(!groups || groups.length === 0) && (
                  <small style={{ color: '#7f8c8d' }}>No groups available</small>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input
                  type="checkbox"
                  checked={formData.is_published}
                  onChange={e => setFormData({ ...formData, is_published: e.target.checked })}
                />
                Published
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <input
                  type="checkbox"
                  checked={formData.is_featured}
                  onChange={e => setFormData({ ...formData, is_featured: e.target.checked })}
                />
                Featured (Top KB)
              </label>
              <button type="submit" className="btn btn-success" disabled={createMutation.isPending || updateMutation.isPending}>
                {editingId ? 'Update Article' : 'Create Article'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => { setShowForm(false); resetForm(); setEditingId(null) }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Search and Filter */}
      {!showForm && (
        <>
          <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
                <label className="form-label">Search</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search by title, slug, or content..."
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0, minWidth: '130px' }}>
                <label className="form-label">Status</label>
                <select
                  className="form-select"
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value)}
                >
                  <option value="published">Published</option>
                  <option value="draft">Draft</option>
                  <option value="">All</option>
                </select>
              </div>
              {(searchInput || statusFilter !== 'published') && (
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => { setSearchInput(''); setSearchTerm(''); setStatusFilter('published') }}
                  style={{ marginBottom: 0 }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Articles Table */}
          <div className="card">
            <h3 className="card-title" style={{ margin: 0 }}>Knowledge Base Articles ({filteredArticles.length})</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Slug</th>
                  <th>Service</th>
                  <th>Visible To</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredArticles.length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: '#6c757d' }}>No articles match your filters.</td></tr>
                )}
                {filteredArticles.map(article => (
                  <tr key={article.id}>
                    <td><strong>{article.title}</strong></td>
                    <td><code>{article.slug}</code></td>
                    <td>{article.service ? `${article.service.icon} ${article.service.name}` : '—'}</td>
                    <td>
                      {(article.allowed_groups || []).length > 0
                        ? article.allowed_groups.map((g: any) => (
                            <span key={g.id} className="badge badge-info" style={{ marginRight: '0.25rem' }}>{g.name}</span>
                          ))
                        : <span className="badge badge-success">All</span>
                      }
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                        <span className={`badge ${article.is_published ? 'badge-success' : 'badge-warning'}`}>
                          {article.is_published ? 'Published' : 'Draft'}
                        </span>
                        {article.is_featured && (
                          <span className="badge badge-info">Featured</span>
                        )}
                      </div>
                    </td>
                    <td>{article.updated_at ? new Date(article.updated_at).toLocaleDateString() : '—'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.3rem' }}>
                        <button className="btn btn-sm btn-primary" onClick={() => editArticle(article)}>Edit</button>
                        <button className="btn btn-sm btn-danger" onClick={() => deleteMutation.mutate(article.id)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
