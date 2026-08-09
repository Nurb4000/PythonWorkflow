import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { adminApi } from '../services/api'
import axios from 'axios'

interface FormUploadRow {
  id: number
  original_name: string
  stored_name: string
  content_type: string
  size_bytes: number
  uploaded_by: number | null
  uploader_username: string | null
  created_at: string
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export const UploadsAdmin: React.FC = () => {
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin-form-uploads', search],
    queryFn: async () => {
      const response = await adminApi.listFormUploads({ q: search, limit: 500 })
      return response.data as { total: number; items: FormUploadRow[] }
    }
  })

  const items = useMemo(() => data?.items || [], [data])

  const downloadFile = async (storedName: string) => {
    try {
      const token = localStorage.getItem('token')
      const res = await axios.get(`/api/forms/download/${encodeURIComponent(storedName)}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      const contentDisposition = res.headers['content-disposition'] || ''
      const match = contentDisposition.match(/filename="?([^";]+)"?/)
      a.download = match ? match[1] : storedName
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Download failed')
    }
  }

  return (
    <div className="page-container">
      <h2>Uploaded Files</h2>
      <p style={{ color: '#7f8c8d', marginTop: '0.5rem' }}>
        All files uploaded via forms. Total: {data?.total ?? 0}
      </p>

      <form
        style={{ margin: '1rem 0', display: 'flex', gap: '0.5rem' }}
        onSubmit={(e) => { e.preventDefault(); setSearch(q) }}
      >
        <input
          className="form-input"
          style={{ maxWidth: '300px' }}
          placeholder="Search by file name..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button type="submit" className="btn btn-primary">Search</button>
        {search && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => { setQ(''); setSearch('') }}
          >
            Clear
          </button>
        )}
      </form>

      {isLoading ? (
        <p>Loading uploads...</p>
      ) : items.length === 0 ? (
        <p style={{ color: '#7f8c8d' }}>No files uploaded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>File</th>
              <th>Size</th>
              <th>Type</th>
              <th>Uploaded By</th>
              <th>Uploaded At</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody>
            {items.map((file) => (
              <tr key={file.id}>
                <td>{file.original_name}</td>
                <td>{formatSize(file.size_bytes)}</td>
                <td>{file.content_type || '-'}</td>
                <td>{file.uploader_username || `#${file.uploaded_by}`}</td>
                <td>{file.created_at ? new Date(file.created_at).toLocaleString() : '-'}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => downloadFile(file.stored_name)}
                  >
                    Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
