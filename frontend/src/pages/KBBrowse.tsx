import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const API_URL = '/api'

interface KbArticle {
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

export const KBBrowse: React.FC = () => {
  const navigate = useNavigate()
  const [featuredArticles, setFeaturedArticles] = useState<KbArticle[]>([])
  const [allArticles, setAllArticles] = useState<KbArticle[]>([])
  const [loading, setLoading] = useState(true)
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [activeTab, setActiveTab] = useState<'featured' | 'all'>('featured')
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setSearchTerm(searchInput), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchInput])

  useEffect(() => {
    loadArticles()
  }, [])

  const loadArticles = async () => {
    try {
      const token = localStorage.getItem('token')
      const [featuredRes, allRes] = await Promise.all([
        axios.get(`${API_URL}/kb-articles/featured`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API_URL}/kb-articles`, { headers: { Authorization: `Bearer ${token}` } }),
      ])
      setFeaturedArticles(featuredRes.data as KbArticle[])
      setAllArticles(allRes.data as KbArticle[])
    } catch (error) {
      console.error('Failed to load KB articles:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredArticles = (activeTab === 'featured' ? featuredArticles : allArticles).filter(article => {
    if (!searchTerm) return true
    const q = searchTerm.toLowerCase()
    return (
      article.title.toLowerCase().includes(q) ||
      article.slug.toLowerCase().includes(q) ||
      (article.content || '').toLowerCase().includes(q)
    )
  })

  const handleArticleClick = (slug: string) => {
    navigate(`/kb/${slug}`)
  }

  if (loading) {
    return <div className="loading">Loading Knowledge Base...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>Knowledge Base</h2>
      </div>

      {/* Search */}
      <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label className="form-label">Search for Helpful Knowledge Articles</label>
            <input
              type="text"
              className="form-input"
              placeholder="Search by title or content..."
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
            />
          </div>
          {searchInput && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => { setSearchInput(''); setSearchTerm('') }}
              style={{ marginBottom: 0 }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '2px solid #dee2e6' }}>
        <button
          className="btn"
          style={{
            borderBottom: activeTab === 'featured' ? '2px solid #3498db' : '2px solid transparent',
            color: activeTab === 'featured' ? '#3498db' : '#6c757d',
            backgroundColor: 'transparent',
            marginBottom: '-2px',
            fontWeight: activeTab === 'featured' ? 700 : 400,
          }}
          onClick={() => setActiveTab('featured')}
        >
          Featured ({featuredArticles.length})
        </button>
        <button
          className="btn"
          style={{
            borderBottom: activeTab === 'all' ? '2px solid #3498db' : '2px solid transparent',
            color: activeTab === 'all' ? '#3498db' : '#6c757d',
            backgroundColor: 'transparent',
            marginBottom: '-2px',
            fontWeight: activeTab === 'all' ? 700 : 400,
          }}
          onClick={() => setActiveTab('all')}
        >
          All Articles ({allArticles.length})
        </button>
      </div>

      {/* Articles List */}
      {filteredArticles.length === 0 && searchTerm.trim() ? (
        <div className="card" style={{ textAlign: 'center', padding: '2rem', opacity: 0.7 }}>
          No articles match "{searchTerm}"
        </div>
      ) : filteredArticles.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', opacity: 0.7 }}>
          {activeTab === 'featured'
            ? 'No featured articles yet. Check back soon or browse all articles.'
            : 'No knowledge base articles available yet.'}
        </div>
      ) : (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem'
        }}>
          {filteredArticles.map(article => (
            <div
              key={article.id}
              className="card"
              style={{
                cursor: 'pointer',
                transition: 'box-shadow 0.2s',
                borderLeft: article.is_featured ? '4px solid #3498db' : undefined,
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
              }}
              onClick={() => handleArticleClick(article.slug)}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = '0 2px 12px rgba(0,0,0,0.1)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = '' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '1.3rem' }}>{article.is_featured ? '⭐' : '📖'}</span>
                <h3 className="card-title" style={{ margin: 0, fontSize: '1rem', flex: 1 }}>
                  {article.title}
                </h3>
              </div>
              <p style={{ margin: 0, opacity: 0.7, fontSize: '0.85rem', flex: 1, lineHeight: 1.4 }}>
                {article.content ? article.content.slice(0, 120).replace(/[#*`]/g, '') + '...' : 'No content'}
              </p>
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                {article.service && (
                  <span className="badge badge-info">{article.service.icon} {article.service.name}</span>
                )}
                {article.is_featured && (
                  <span className="badge badge-success">Featured</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
