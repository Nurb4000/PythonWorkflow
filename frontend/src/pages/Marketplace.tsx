import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { marketplaceApi } from '../services/api'
import { useAuth } from '../components/Auth'

interface MarketplaceItem {
  id: number
  item_type: string
  name: string
  description: string
  category: string
  tags: string[]
  author_id: number
  author_name?: string
  version: number
  content_format: string
  node_type: string | null
  status: string
  is_active: boolean
  downloads_count: number
  created_at: string
  updated_at: string
}

interface SavedNode {
  id: number
  user_id: number
  step_type: string
  title: string
  description: string
  definition: Record<string, any>
  condition_expr: string
  is_enabled: boolean
  max_retries: number
  retry_delay_seconds: number
  failure_hook_url: string
  source_marketplace_item_id: number | null
  created_at: string
}

interface AuditResult {
  item_type: string
  step_types: string[]
  external_urls: string[]
  has_custom_code: boolean
  has_database_query: boolean
  forms_referenced: string[]
  groups_referenced: string[]
  email_recipients: string[]
  warnings: string[]
  workflow_name?: string
  node_title?: string
  steps_count?: number
  forms_count?: number
  groups_count?: number
  schedules_count?: number
}

type ActiveTab = 'workflows' | 'nodes' | 'my-nodes'

export const Marketplace: React.FC = () => {
  const { user } = useAuth()
  const canDevelop = user?.role === 'admin' || user?.role === 'developer'
  const isAdmin = user?.role === 'admin'
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<ActiveTab>('workflows')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [sortBy, setSortBy] = useState('updated_at')
  const [sortOrder, setSortOrder] = useState('desc')
  const [offset, setOffset] = useState(0)
  const [selectedItem, setSelectedItem] = useState<MarketplaceItem | null>(null)
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null)
  const [installConfirmed, setInstallConfirmed] = useState(false)
  const [installResult, setInstallResult] = useState<any>(null)
  const [installOptions, setInstallOptions] = useState({
    on_conflict: 'copy',
    environment: 'preserve',
    create_forms: true,
    create_groups: true,
    match_users_by_email: true,
  })
  const [error, setError] = useState('')

  const limit = 20

  // Fetch marketplace items
  const { data: itemsData, isLoading: itemsLoading } = useQuery({
    queryKey: ['marketplace-items', activeTab === 'my-nodes' ? null : activeTab, searchTerm, selectedCategory, sortBy, sortOrder, offset],
    queryFn: async () => {
      if (activeTab === 'my-nodes') {
        return { items: [], total: 0 }
      }
      const params: any = {
        item_type: activeTab === 'workflows' ? 'workflow' : 'node',
        sort_by: sortBy,
        sort_order: sortOrder,
        offset,
        limit,
      }
      if (searchTerm) params.search = searchTerm
      if (selectedCategory) params.category = selectedCategory
      const res = await marketplaceApi.listItems(params)
      return res.data
    },
    enabled: activeTab !== 'my-nodes',
  })

  // Fetch categories
  const { data: categoriesData } = useQuery({
    queryKey: ['marketplace-categories'],
    queryFn: async () => {
      const res = await marketplaceApi.getCategories()
      return res.data
    },
  })

  // Fetch my nodes
  const { data: myNodesData, isLoading: myNodesLoading } = useQuery({
    queryKey: ['my-nodes'],
    queryFn: async () => {
      const res = await marketplaceApi.listMyNodes()
      return res.data as SavedNode[]
    },
    enabled: activeTab === 'my-nodes',
  })

  // Fetch item detail
  const { data: itemDetail } = useQuery({
    queryKey: ['marketplace-item', selectedItem?.id],
    queryFn: async () => {
      const res = await marketplaceApi.getItem(selectedItem!.id)
      return res.data as MarketplaceItem
    },
    enabled: !!selectedItem,
  })

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: (id: number) => marketplaceApi.previewItem(id),
    onSuccess: (data) => {
      setAuditResult(data.data as AuditResult)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Preview failed')
    },
  })

  // Install mutation
  const installMutation = useMutation({
    mutationFn: () => {
      if (!selectedItem) return Promise.reject('No item selected')
      const params: any = {}
      if (selectedItem.item_type === 'workflow') {
        params.on_conflict = installOptions.on_conflict
        params.environment = installOptions.environment
        params.create_forms = installOptions.create_forms
        params.create_groups = installOptions.create_groups
        params.match_users_by_email = installOptions.match_users_by_email
      }
      return marketplaceApi.installItem(selectedItem.id, params)
    },
    onSuccess: (data) => {
      setInstallResult(data.data)
      queryClient.invalidateQueries({ queryKey: ['marketplace-items'] })
      queryClient.invalidateQueries({ queryKey: ['my-nodes'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Install failed')
    },
  })

  // Delete my node mutation
  const deleteNodeMutation = useMutation({
    mutationFn: (id: number) => marketplaceApi.deleteMyNode(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-nodes'] })
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Delete failed')
    },
  })

  // Delete marketplace item mutation
  const deleteItemMutation = useMutation({
    mutationFn: (id: number) => marketplaceApi.deleteItem(id, false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace-items'] })
      handleCloseDetail()
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Delete failed')
    },
  })

  // Archive marketplace item mutation (admin)
  const archiveItemMutation = useMutation({
    mutationFn: (id: number) => marketplaceApi.deleteItem(id, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace-items'] })
      handleCloseDetail()
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Archive failed')
    },
  })

  // Update marketplace item mutation
  const [editMode, setEditMode] = useState(false)
  const [editForm, setEditForm] = useState({ name: '', description: '', category: '', tags: '' })
  const updateItemMutation = useMutation({
    mutationFn: () => {
      if (!itemDetail) throw new Error('No item')
      return marketplaceApi.updateItem(itemDetail.id, {
        name: editForm.name,
        description: editForm.description,
        category: editForm.category,
        tags: editForm.tags.split(',').map((t: string) => t.trim()).filter(Boolean),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace-items'] })
      queryClient.invalidateQueries({ queryKey: ['marketplace-item', itemDetail?.id] })
      setEditMode(false)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Update failed')
    },
  })

  // Fetch audit when item detail loads
  useEffect(() => {
    if (itemDetail && !previewMutation.isPending) {
      setAuditResult(null)
      setInstallConfirmed(false)
      setInstallResult(null)
      setError('')
      setEditMode(false)
      setEditForm({
        name: itemDetail.name || '',
        description: itemDetail.description || '',
        category: itemDetail.category || 'General',
        tags: (itemDetail.tags || []).join(', '),
      })
      previewMutation.mutate(itemDetail.id)
    }
  }, [itemDetail?.id])

  const handleSelectItem = (item: MarketplaceItem) => {
    setSelectedItem(item)
    setSearchTerm('')
    setOffset(0)
  }

  const handleCloseDetail = () => {
    setSelectedItem(null)
    setAuditResult(null)
    setInstallConfirmed(false)
    setInstallResult(null)
    setError('')
  }

  const handleInstall = () => {
    if (!installConfirmed) {
      setInstallConfirmed(true)
      return
    }
    installMutation.mutate()
  }

  const handlePageChange = (newOffset: number) => {
    setOffset(newOffset)
  }

  const totalPages = Math.ceil((itemsData?.total || 0) / limit)

  const renderItemTypeBadge = (type: string) => {
    if (type === 'workflow') {
      return <span className="badge badge-info">Workflow</span>
    }
    return <span className="badge badge-success">Node</span>
  }

  const renderCategoryBadge = (category: string) => {
    return <span className="badge badge-secondary">{category}</span>
  }

  // ── My Nodes tab content ────────────────────────────────────────────
  const renderMyNodes = () => (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>My Nodes Library</h2>
        <button
          className="btn btn-secondary"
          onClick={() => { setActiveTab('workflows'); setOffset(0); setSelectedItem(null) }}
        >
          ← Back to Marketplace
        </button>
      </div>

      {myNodesLoading && <div className="loading">Loading your nodes...</div>}

      {!myNodesLoading && (!myNodesData || myNodesData.length === 0) && (
        <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: '#7f8c8d', fontSize: '1.1rem' }}>No saved nodes yet.</p>
          <p style={{ color: '#95a5a6' }}>Install node templates from the marketplace to save them here, or save nodes from the designer.</p>
        </div>
      )}

      {!myNodesLoading && myNodesData && myNodesData.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {myNodesData.map((node: SavedNode) => (
            <div key={node.id} className="card" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                <h4 style={{ margin: 0 }}>{node.title}</h4>
                <span className="badge badge-info">{node.step_type}</span>
              </div>
              {node.description && (
                <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0' }}>{node.description}</p>
              )}
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
                {node.max_retries > 0 && (
                  <span className="badge badge-secondary">Retries: {node.max_retries}</span>
                )}
                {node.is_enabled ? (
                  <span className="badge badge-success">Enabled</span>
                ) : (
                  <span className="badge badge-warning">Disabled</span>
                )}
                {node.source_marketplace_item_id && (
                  <span className="badge badge-secondary" title="From marketplace">Marketplace import</span>
                )}
              </div>
              <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <small style={{ color: '#95a5a6' }}>
                  {new Date(node.created_at).toLocaleDateString()}
                </small>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={() => {
                    if (window.confirm(`Delete "${node.title}" from your library?`)) {
                      deleteNodeMutation.mutate(node.id)
                    }
                  }}
                  disabled={deleteNodeMutation.isPending}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  // ── Main browse view ────────────────────────────────────────────────
  return (
    <div>
      <div className="card-header">
        <h2>Marketplace</h2>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '2px solid #eee' }}>
        {([['workflows', 'Workflows'], ['nodes', 'Nodes'], ['my-nodes', 'My Nodes']] as [ActiveTab, string][]).map(([tab, label]) => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setOffset(0); setSelectedItem(null) }}
            style={{
              padding: '0.75rem 1.5rem',
              border: 'none',
              borderBottom: activeTab === tab ? '3px solid #3498db' : '3px solid transparent',
              background: 'none',
              cursor: 'pointer',
              fontWeight: activeTab === tab ? 700 : 400,
              color: activeTab === tab ? '#2c3e50' : '#7f8c8d',
              fontSize: '1rem',
              transition: 'all 0.2s',
            }}
          >
            {label}
            {tab !== 'my-nodes' && (
              <span style={{ marginLeft: '0.5rem', fontSize: '0.85rem', color: '#95a5a6' }}>
                {itemsData?.total || 0}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}

      {/* Search and filters */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Search</label>
            <input
              type="text"
              className="form-input"
              placeholder={`Search ${activeTab === 'workflows' ? 'workflows' : 'nodes'}...`}
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setOffset(0) }}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Category</label>
            <select
              className="form-select"
              value={selectedCategory}
              onChange={(e) => { setSelectedCategory(e.target.value); setOffset(0) }}
              style={{ minWidth: '180px' }}
            >
              <option value="">All Categories</option>
              {(categoriesData?.allCategories || []).map((cat: string) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Sort By</label>
            <select
              className="form-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{ minWidth: '150px' }}
            >
              <option value="updated_at">Last Updated</option>
              <option value="created_at">Created Date</option>
              <option value="name">Name</option>
              <option value="downloads">Downloads</option>
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Direction</label>
            <select
              className="form-select"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              style={{ minWidth: '120px' }}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </div>
          {(searchTerm || selectedCategory) && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSearchTerm(''); setSelectedCategory(''); setOffset(0) }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>

        {/* Tag cloud */}
        {categoriesData?.tagCloud && categoriesData.tagCloud.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <small style={{ color: '#7f8c8d', display: 'block', marginBottom: '0.5rem' }}>Popular tags:</small>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {categoriesData.tagCloud.slice(0, 15).map((tag: { name: string; count: number }) => (
                <button
                  key={tag.name}
                  onClick={() => { setSearchTerm(tag.name); setOffset(0) }}
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: '12px',
                    border: '1px solid #ddd',
                    background: '#f8f9fa',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    color: '#555',
                  }}
                >
                  {tag.name} <span style={{ color: '#999' }}>({tag.count})</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

{/* Items grid or My Nodes */}
      {activeTab === 'my-nodes' ? renderMyNodes() : (
        <>
          {itemsLoading && <div className="loading">Loading marketplace items...</div>}

          {!itemsLoading && (!itemsData || itemsData.items.length === 0) && (
            <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
              <p style={{ color: '#7f8c8d', fontSize: '1.1rem' }}>
                No {activeTab === 'workflows' ? 'workflows' : 'nodes'} found.
              </p>
              {(searchTerm || selectedCategory) && (
                <p style={{ color: '#95a5a6' }}>Try adjusting your search or filters.</p>
              )}
            </div>
          )}

          {!itemsLoading && itemsData && itemsData.items.length > 0 && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
                {itemsData.items.map((item: MarketplaceItem) => (
                  <div
                    key={item.id}
                    className="card"
                    style={{ padding: '1.25rem', cursor: 'pointer', transition: 'box-shadow 0.2s', border: '1px solid #eee' }}
                    onClick={() => handleSelectItem(item)}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                      {renderItemTypeBadge(item.item_type)}
                      <span style={{ fontSize: '0.8rem', color: '#95a5a6' }}>v{item.version}</span>
                    </div>
                    <h4 style={{ margin: '0.5rem 0' }}>{item.name}</h4>
                    {item.description && (
                      <p style={{ color: '#666', fontSize: '0.9rem', margin: '0.5rem 0', lineHeight: 1.4 }}>
                        {item.description.length > 120 ? item.description.substring(0, 120) + '...' : item.description}
                      </p>
                    )}
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
                      {renderCategoryBadge(item.category)}
                      {item.node_type && (
                        <span className="badge badge-info">{item.node_type}</span>
                      )}
                    </div>
                    {item.tags && item.tags.length > 0 && (
                      <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                        {item.tags.slice(0, 3).map((tag: string) => (
                          <span key={tag} style={{ fontSize: '0.75rem', color: '#3498db', background: '#ebf5fb', padding: '0.15rem 0.5rem', borderRadius: '8px' }}>
                            {tag}
                          </span>
                        ))}
                        {item.tags.length > 3 && (
                          <span style={{ fontSize: '0.75rem', color: '#95a5a6' }}>+{item.tags.length - 3}</span>
                        )}
                      </div>
                    )}
                    <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <small style={{ color: '#95a5a6' }}>
                        {item.author_name || 'Unknown'} &middot; {new Date(item.updated_at).toLocaleDateString()}
                      </small>
                      <small style={{ color: '#3498db' }}>
                        {item.downloads_count} downloads
                      </small>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
                  {offset > 0 && (
                    <button className="btn btn-sm btn-secondary" onClick={() => handlePageChange(offset - limit)}>
                      Previous
                    </button>
                  )}
                  {Array.from({ length: totalPages }, (_, i) => i).map(page => (
                    <button
                      key={page}
                      className={`btn btn-sm ${page * limit === offset ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => handlePageChange(page * limit)}
                    >
                      {page + 1}
                    </button>
                  ))}
                  {offset + limit < (itemsData.total || 0) && (
                    <button className="btn btn-sm btn-secondary" onClick={() => handlePageChange(offset + limit)}>
                      Next
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* Item detail modal */}
      {selectedItem && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000, overflow: 'auto', padding: '2rem',
          }}
          onClick={handleCloseDetail}
        >
          <div
            className="card"
            style={{ maxWidth: '700px', width: '100%', maxHeight: '85vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ marginBottom: '0.5rem' }}>
                  {renderItemTypeBadge(selectedItem.item_type)}
                  {selectedItem.node_type && (
                    <span className="badge badge-info" style={{ marginLeft: '0.5rem' }}>{selectedItem.node_type}</span>
                  )}
                </div>
                <h3 style={{ margin: 0 }}>{itemDetail?.name || selectedItem.name}</h3>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {canDevelop && itemDetail && (
                  <>
                    {!editMode ? (
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => setEditMode(true)}
                        title="Edit metadata"
                      >
                        ✎ Edit
                      </button>
                    ) : null}
                    {isAdmin && itemDetail && (
                      <button
                        className="btn btn-sm btn-warning"
                        onClick={() => {
                          if (window.confirm(`Archive "${itemDetail.name}"? It will be hidden from the marketplace but not permanently deleted.`)) {
                            archiveItemMutation.mutate(itemDetail.id)
                          }
                        }}
                        disabled={archiveItemMutation.isPending}
                        title="Archive item (admin)"
                      >
                        Archive
                      </button>
                    )}
                    {(itemDetail.author_id === user?.id || isAdmin) && itemDetail && (
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => {
                          if (window.confirm(`Permanently delete "${itemDetail.name}"? This cannot be undone.`)) {
                            deleteItemMutation.mutate(itemDetail.id)
                          }
                        }}
                        disabled={deleteItemMutation.isPending}
                        title="Delete item"
                      >
                        Delete
                      </button>
                    )}
                  </>
                )}
                <button
                  onClick={handleCloseDetail}
                  style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#999', lineHeight: 1 }}
                >
                  &times;
                </button>
              </div>
            </div>

            {itemDetail && (
              <>
                <p style={{ color: '#666', margin: '1rem 0' }}>{itemDetail.description}</p>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                  {renderCategoryBadge(itemDetail.category)}
                  <span style={{ color: '#95a5a6', fontSize: '0.85rem', alignSelf: 'center' }}>
                    v{itemDetail.version} &middot; {itemDetail.downloads_count} downloads &middot; by {itemDetail.author_name || 'Unknown'}
                  </span>
                </div>

                {itemDetail.tags && itemDetail.tags.length > 0 && (
                  <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                    {itemDetail.tags.map((tag: string) => (
                      <span key={tag} style={{ fontSize: '0.8rem', color: '#3498db', background: '#ebf5fb', padding: '0.2rem 0.6rem', borderRadius: '10px' }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Edit metadata form */}
                {editMode && canDevelop && (
                  <div style={{ background: '#f0f3f5', padding: '1rem', borderRadius: '6px', marginBottom: '1rem' }}>
                    <h4 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Edit Metadata</h4>
                    <div className="form-group">
                      <label className="form-label">Name</label>
                      <input
                        type="text"
                        className="form-input"
                        value={editForm.name}
                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Description</label>
                      <textarea
                        className="form-textarea"
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        rows={2}
                      />
                    </div>
                    <div className="grid grid-2">
                      <div className="form-group">
                        <label className="form-label">Category</label>
                        <select
                          className="form-select"
                          value={editForm.category}
                          onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                        >
                          {(categoriesData?.allCategories || []).map((cat: string) => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </div>
                      <div className="form-group">
                        <label className="form-label">Tags (comma-separated)</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editForm.tags}
                          onChange={(e) => setEditForm({ ...editForm, tags: e.target.value })}
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                      <button
                        className="btn btn-primary"
                        onClick={() => updateItemMutation.mutate()}
                        disabled={updateItemMutation.isPending || !editForm.name.trim()}
                      >
                        {updateItemMutation.isPending ? 'Saving...' : 'Save Changes'}
                      </button>
                      <button
                        className="btn btn-secondary"
                        onClick={() => setEditMode(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Audit preview */}
                {previewMutation.isPending && (
                  <div style={{ textAlign: 'center', padding: '1rem' }}>Loading audit...</div>
                )}

                {auditResult && (
                  <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '6px', marginBottom: '1rem' }}>
                    <h4 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Security Review</h4>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                      <div>
                        <strong style={{ fontSize: '0.85rem', color: '#555' }}>Step Types</strong>
                        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                          {auditResult.step_types.map(st => (
                            <span key={st} className="badge badge-secondary" style={{ fontSize: '0.75rem' }}>{st}</span>
                          ))}
                        </div>
                      </div>

                      {auditResult.steps_count !== undefined && (
                        <div>
                          <strong style={{ fontSize: '0.85rem', color: '#555' }}>Steps</strong>
                          <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>{auditResult.steps_count}</p>
                        </div>
                      )}

                      {auditResult.schedules_count !== undefined && (
                        <div>
                          <strong style={{ fontSize: '0.85rem', color: '#555' }}>Schedules</strong>
                          <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>{auditResult.schedules_count}</p>
                        </div>
                      )}

                      {auditResult.forms_count !== undefined && (
                        <div>
                          <strong style={{ fontSize: '0.85rem', color: '#555' }}>Forms</strong>
                          <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>{auditResult.forms_count}</p>
                        </div>
                      )}

                      {auditResult.groups_count !== undefined && (
                        <div>
                          <strong style={{ fontSize: '0.85rem', color: '#555' }}>Groups</strong>
                          <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>{auditResult.groups_count}</p>
                        </div>
                      )}
                    </div>

                    {auditResult.external_urls.length > 0 && (
                      <div style={{ marginTop: '0.75rem' }}>
                        <strong style={{ fontSize: '0.85rem', color: '#555' }}>External URLs</strong>
                        <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem', fontSize: '0.85rem' }}>
                          {auditResult.external_urls.map((url, i) => (
                            <li key={i} style={{ color: '#e67e22' }}>{url}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {auditResult.email_recipients.length > 0 && (
                      <div style={{ marginTop: '0.5rem' }}>
                        <strong style={{ fontSize: '0.85rem', color: '#555' }}>Email Recipients</strong>
                        <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>{auditResult.email_recipients.join(', ')}</p>
                      </div>
                    )}

                    {auditResult.has_custom_code && (
                      <div style={{ marginTop: '0.5rem' }}>
                        <span className="badge badge-warning">Contains custom code</span>
                      </div>
                    )}

                    {auditResult.has_database_query && (
                      <div style={{ marginTop: '0.5rem' }}>
                        <span className="badge badge-warning">Contains database queries</span>
                      </div>
                    )}

                    {auditResult.warnings.length > 0 && (
                      <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#fef9e7', borderRadius: '4px' }}>
                        <strong style={{ color: '#f39c12', fontSize: '0.85rem' }}>Warnings:</strong>
                        <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem', fontSize: '0.85rem' }}>
                          {auditResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Install options for workflows */}
                {selectedItem.item_type === 'workflow' && !installResult && (
                  <div style={{ background: '#f0f3f5', padding: '1rem', borderRadius: '6px', marginBottom: '1rem' }}>
                    <h4 style={{ marginTop: 0, marginBottom: '0.75rem' }}>Install Options</h4>
                    <div className="grid grid-2">
                      <div className="form-group">
                        <label className="form-label">Target Environment</label>
                        <select
                          className="form-select"
                          value={installOptions.environment}
                          onChange={(e) => setInstallOptions({ ...installOptions, environment: e.target.value })}
                        >
                          <option value="preserve">Preserve Source</option>
                          <option value="test">Force Test</option>
                          <option value="production">Force Production</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label className="form-label">On Name Conflict</label>
                        <select
                          className="form-select"
                          value={installOptions.on_conflict}
                          onChange={(e) => setInstallOptions({ ...installOptions, on_conflict: e.target.value })}
                        >
                          <option value="copy">Create as "(Copy)"</option>
                          <option value="skip">Skip</option>
                          <option value="overwrite">Overwrite Existing</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={installOptions.create_forms}
                            onChange={(e) => setInstallOptions({ ...installOptions, create_forms: e.target.checked })}
                          />
                          Create missing forms
                        </label>
                      </div>
                      <div className="form-group">
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={installOptions.create_groups}
                            onChange={(e) => setInstallOptions({ ...installOptions, create_groups: e.target.checked })}
                          />
                          Create missing groups
                        </label>
                      </div>
                      <div className="form-group">
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={installOptions.match_users_by_email}
                            onChange={(e) => setInstallOptions({ ...installOptions, match_users_by_email: e.target.checked })}
                          />
                          Match users by email
                        </label>
                      </div>
                    </div>
                  </div>
                )}

                {/* Install button */}
                {!installResult && (
                  <div style={{ marginTop: '1rem' }}>
                    {!installConfirmed ? (
                      <button
                        className="btn btn-success"
                        onClick={handleInstall}
                        disabled={!auditResult || installMutation.isPending}
                        style={{ width: '100%' }}
                      >
                        Review & Install
                      </button>
                    ) : (
                      <div style={{ background: '#fef9e7', padding: '1rem', borderRadius: '6px' }}>
                        <p style={{ margin: '0 0 0.75rem', color: '#856404' }}>
                          You have reviewed the security audit above. Proceed with installation?
                        </p>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button
                            className="btn btn-success"
                            onClick={handleInstall}
                            disabled={installMutation.isPending}
                          >
                            {installMutation.isPending
                              ? (selectedItem.item_type === 'workflow' ? 'Installing Workflow...' : 'Installing Node...')
                              : `Yes, Install ${selectedItem.item_type === 'workflow' ? 'Workflow' : 'Node'}`}
                          </button>
                          <button
                            className="btn btn-secondary"
                            onClick={() => setInstallConfirmed(false)}
                            disabled={installMutation.isPending}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Install result */}
                {installResult && (
                  <div style={{ marginTop: '1rem', background: installResult.import_result?.errors?.length ? '#fdf2f2' : '#f0fff4', padding: '1rem', borderRadius: '6px' }}>
                    <h4 style={{ marginTop: 0, color: '#27ae60' }}>Installation Complete</h4>

                    {installResult.item_type === 'workflow' && installResult.import_result && (
                      <>
                        {installResult.import_result.workflowsCreated?.length > 0 && (
                          <p style={{ color: '#27ae60' }}>
                            Created: {installResult.import_result.workflowsCreated.join(', ')}
                          </p>
                        )}
                        {installResult.import_result.workflowsSkipped?.length > 0 && (
                          <p style={{ color: '#f39c12' }}>
                            Skipped: {installResult.import_result.workflowsSkipped.join(', ')}
                          </p>
                        )}
                        {installResult.import_result.formsCreated?.length > 0 && (
                          <p style={{ color: '#27ae60' }}>Forms created: {installResult.import_result.formsCreated.length}</p>
                        )}
                        {installResult.import_result.groupsCreated?.length > 0 && (
                          <p style={{ color: '#27ae60' }}>Groups created: {installResult.import_result.groupsCreated.length}</p>
                        )}
                        <p>Steps: {installResult.import_result.stepsCount} | Schedules: {installResult.import_result.schedulesCount}</p>
                        {installResult.import_result.warnings?.length > 0 && (
                          <div style={{ marginTop: '0.5rem' }}>
                            <strong style={{ color: '#f39c12' }}>Warnings:</strong>
                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem' }}>
                              {installResult.import_result.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                            </ul>
                          </div>
                        )}
                        {installResult.import_result.errors?.length > 0 && (
                          <div style={{ marginTop: '0.5rem' }}>
                            <strong style={{ color: '#e74c3c' }}>Errors:</strong>
                            <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem' }}>
                              {installResult.import_result.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
                            </ul>
                          </div>
                        )}
                      </>
                    )}

                    {installResult.item_type === 'node' && installResult.saved_node && (
                      <>
                        <p style={{ color: '#27ae60' }}>
                          Node "{installResult.saved_node.title}" saved to your My Nodes library.
                        </p>
                        <p style={{ fontSize: '0.9rem', color: '#666' }}>
                          Step type: {installResult.saved_node.step_type}
                          {installResult.saved_node.max_retries > 0 && ` | Retries: ${installResult.saved_node.max_retries}`}
                        </p>
                      </>
                    )}

                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                      {installResult.item_type === 'workflow' && (
                        <Link to="/workflows" className="btn btn-primary">
                          View Workflows
                        </Link>
                      )}
                      {installResult.item_type === 'node' && (
                        <button className="btn btn-primary" onClick={() => { setActiveTab('my-nodes'); handleCloseDetail() }}>
                          View My Nodes
                        </button>
                      )}
                      <button className="btn btn-secondary" onClick={handleCloseDetail}>
                        Close
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
