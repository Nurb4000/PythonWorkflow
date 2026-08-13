import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { kbApi } from '../services/api'

interface KbArticle {
  id: number
  title: string
  slug: string
  content: string
  service_id: number | null
  is_published: boolean
  service?: { id: number; name: string; key: string; icon: string }
}

export const KBArticleViewer: React.FC = () => {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [article, setArticle] = useState<KbArticle | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    kbApi.getArticleBySlug(slug).then(res => {
      setArticle(res.data as KbArticle)
    }).catch(() => {
      setArticle(null)
    }).finally(() => {
      setLoading(false)
    })
  }, [slug])

  if (loading) {
    return <div className="loading">Loading article...</div>
  }

  if (!article) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <h2>Article Not Found</h2>
        <p>The requested help article doesn't exist or hasn't been published yet.</p>
        <button className="btn btn-primary" onClick={() => navigate('/catalog')}>Back to Catalog</button>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: '1rem' }}>
        <button className="btn btn-sm btn-secondary" onClick={() => navigate(-1)}>
          ← Back
        </button>
        {article.service && (
          <button
            className="btn btn-sm btn-primary"
            onClick={() => navigate('/catalog')}
            style={{ marginLeft: '0.5rem' }}
          >
            {article.service.icon} {article.service.name}
          </button>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginBottom: '0.5rem' }}>{article.title}</h2>
        {article.service && (
          <span className="badge badge-info" style={{ marginBottom: '1rem', display: 'inline-block' }}>
            {article.service.icon} {article.service.name}
          </span>
        )}
        <div style={{
          marginTop: '1.5rem',
          lineHeight: 1.7,
          whiteSpace: 'pre-wrap',
          fontSize: '0.95rem',
        }}>
          {article.content.split('\n').map((line, i) => {
            if (line.startsWith('### ')) {
              return <h5 key={i} style={{ marginTop: '1.2rem', marginBottom: '0.4rem' }}>{line.replace('### ', '')}</h5>
            }
            if (line.startsWith('## ')) {
              return <h4 key={i} style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>{line.replace('## ', '')}</h4>
            }
            if (line.startsWith('# ')) {
              return <h3 key={i} style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>{line.replace('# ', '')}</h3>
            }
            if (line.startsWith('- ')) {
              return <div key={i} style={{ marginLeft: '1.5rem' }}><span style={{ marginRight: '0.3rem' }}>•</span>{line.substring(2)}</div>
            }
            if (line.trim() === '') {
              return <br key={i} />
            }
            if (line.startsWith('```')) {
              return null
            }
            return <p key={i} style={{ margin: '0.3rem 0' }}>{line}</p>
          })}
        </div>
      </div>
    </div>
  )
}
