import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { useBranding } from '../components/Branding'

const API_URL = '/api'

interface Settings {
  llama_cpp_url: string
  llama_cpp_model: string
  email_smtp_host: string
  email_smtp_port: number
  email_from: string
}

interface ImapSettings {
  imap_monitor_enabled: boolean
  imap_host: string
  imap_port: number
  imap_username: string
  imap_poll_interval: number
  imap_folder: string
  imap_trash_folder: string
  imap_default_workflow_id: string
}

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<Settings>({
    llama_cpp_url: '',
    llama_cpp_model: 'default',
    email_smtp_host: '',
    email_smtp_port: 587,
    email_from: ''
  })
  const [emailPassword, setEmailPassword] = useState('')
  const [imapSettings, setImapSettings] = useState<ImapSettings>({
    imap_monitor_enabled: false,
    imap_host: '',
    imap_port: 993,
    imap_username: '',
    imap_poll_interval: 300,
    imap_folder: 'INBOX',
    imap_trash_folder: 'Trash',
    imap_default_workflow_id: ''
  })
  const [imapPassword, setImapPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState<'success' | 'error'>('success')
  const { branding, refresh: refreshBranding, ready: brandingReady } = useBranding()
  const [brandingForm, setBrandingForm] = useState({ system_name: '' })
  const [logoPreview, setLogoPreview] = useState<string | null>(null)
  const [imapTestResult, setImapTestResult] = useState<any>(null)
  const [imapTesting, setImapTesting] = useState(false)
  const [imapPolling, setImapPolling] = useState(false)
  const [bannerForm, setBannerForm] = useState({
    banner_enabled: false,
    banner_title: '',
    banner_message: '',
    banner_color: '#f39c12',
  })
  const [marketplaceCategories, setMarketplaceCategories] = useState<string[]>([])
  const [newCategory, setNewCategory] = useState('')

  useEffect(() => {
    loadSettings()
    loadImapSettings()
    loadBannerSettings()
    loadMarketplaceCategories()
  }, [])

  useEffect(() => {
    setBrandingForm({ system_name: branding.system_name || '' })
    setLogoPreview(branding.logo_url)
  }, [branding])

  const loadSettings = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/settings`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setSettings(response.data)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadImapSettings = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/settings/imap`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setImapSettings(response.data)
    } catch (error) {
      console.error('Failed to load IMAP settings:', error)
    }
  }

  const loadBannerSettings = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/settings/banner`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setBannerForm(response.data)
    } catch (error) {
      console.error('Failed to load banner settings:', error)
    }
  }

  const handleBannerSave = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/banner`,
        null,
        {
          params: {
            banner_enabled: bannerForm.banner_enabled,
            banner_title: bannerForm.banner_title,
            banner_message: bannerForm.banner_message,
            banner_color: bannerForm.banner_color,
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('Banner settings updated successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to update banner settings')
      setMessageType('error')
    }
  }

  const loadMarketplaceCategories = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get(`${API_URL}/marketplace/categories`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setMarketplaceCategories(response.data.allCategories || [])
    } catch (error) {
      console.error('Failed to load marketplace categories:', error)
    }
  }

  const handleAddCategory = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = newCategory.trim()
    if (!trimmed || marketplaceCategories.includes(trimmed)) return
    const updated = [...marketplaceCategories, trimmed]
    try {
      const token = localStorage.getItem('token')
      await axios.put(`${API_URL}/marketplace/categories`, { categories: updated }, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setMarketplaceCategories(updated)
      setNewCategory('')
      setMessage('Category added successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to add category')
      setMessageType('error')
    }
  }

  const handleRemoveCategory = async (cat: string) => {
    const updated = marketplaceCategories.filter(c => c !== cat)
    try {
      const token = localStorage.getItem('token')
      await axios.put(`${API_URL}/marketplace/categories`, { categories: updated }, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setMarketplaceCategories(updated)
      setMessage('Category removed successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to remove category')
      setMessageType('error')
    }
  }

  const handleLLMUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/llm`,
        null,
        {
          params: {
            llama_cpp_url: settings.llama_cpp_url,
            llama_cpp_model: settings.llama_cpp_model
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('LLM settings updated successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to update LLM settings')
      setMessageType('error')
    }
  }

  const handleEmailUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/email`,
        null,
        {
          params: {
            smtp_host: settings.email_smtp_host,
            smtp_port: settings.email_smtp_port,
            username: '',
            password: emailPassword,
            from_address: settings.email_from
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('Email settings updated successfully')
      setMessageType('success')
      setEmailPassword('')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to update email settings')
      setMessageType('error')
    }
  }

  const handleBrandingSave = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      console.log('Saving branding:', brandingForm)
      const response = await axios.put(
        `${API_URL}/settings/branding`,
        null,
        {
          params: { system_name: brandingForm.system_name },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      console.log('Save response:', response.data)
      // Refresh branding context
      console.log('Calling refreshBranding...')
      await refreshBranding()
      console.log('After refresh, branding context:', branding)
      setMessage('Branding updated successfully')
    } catch (error: any) {
      console.error('Save error:', error.response?.data || error.message)
      setMessage(error.response?.data?.detail || 'Failed to update branding')
      setMessageType('error')
    }
  }

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const token = localStorage.getItem('token')
      const fd = new FormData()
      fd.append('file', file)
      const res = await axios.post(`${API_URL}/settings/branding/logo`, fd, {
        headers: { Authorization: `Bearer ${token}` }
      })
      await refreshBranding()
      setMessage('Logo uploaded successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to upload logo')
      setMessageType('error')
    }
  }

  const handleLogoRemove = async () => {
    try {
      const token = localStorage.getItem('token')
      await axios.delete(`${API_URL}/settings/branding/logo`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      await refreshBranding()
      setMessage('Logo removed successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to remove logo')
      setMessageType('error')
    }
  }

  const handleImapUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem('token')
      await axios.put(
        `${API_URL}/settings/imap`,
        null,
        {
          params: {
            imap_monitor_enabled: imapSettings.imap_monitor_enabled,
            imap_host: imapSettings.imap_host,
            imap_port: imapSettings.imap_port,
            imap_username: imapSettings.imap_username,
            imap_password: imapPassword,
            imap_poll_interval: imapSettings.imap_poll_interval,
            imap_folder: imapSettings.imap_folder,
            imap_trash_folder: imapSettings.imap_trash_folder,
            imap_default_workflow_id: imapSettings.imap_default_workflow_id
          },
          headers: { Authorization: `Bearer ${token}` }
        }
      )
      setMessage('IMAP settings updated successfully')
      setMessageType('success')
      setImapPassword('')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Failed to update IMAP settings')
      setMessageType('error')
    }
  }

  const handleImapTest = async () => {
    setImapTesting(true)
    setImapTestResult(null)
    try {
      const token = localStorage.getItem('token')
      const response = await axios.post(
        `${API_URL}/settings/imap/test`,
        null,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setImapTestResult(response.data)
    } catch (error: any) {
      setImapTestResult({ connected: false, error: error.response?.data?.detail || 'Connection failed' })
    } finally {
      setImapTesting(false)
    }
  }

  const handleImapPollNow = async () => {
    setImapPolling(true)
    try {
      const token = localStorage.getItem('token')
      await axios.post(
        `${API_URL}/settings/imap/poll-now`,
        null,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setMessage('IMAP poll completed successfully')
      setMessageType('success')
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'IMAP poll failed')
      setMessageType('error')
    } finally {
      setImapPolling(false)
    }
  }

  if (loading || !brandingReady) {
    return <div className="loading">Loading settings...</div>
  }

  return (
    <div>
      <div className="card-header">
        <h2>System Settings</h2>
      </div>

      {message && <div className={messageType === 'error' ? 'error' : 'success'} style={{ marginBottom: '1rem' }}>{message}</div>}

      <div className="card">
        <h3 className="card-title">LLM Configuration (llama.cpp)</h3>
        <form onSubmit={handleLLMUpdate}>
          <div className="form-group">
            <label className="form-label">llama.cpp Server URL</label>
            <input
              type="text"
              className="form-input"
              value={settings.llama_cpp_url}
              onChange={(e) => setSettings({...settings, llama_cpp_url: e.target.value})}
              placeholder="http://localhost:8081"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Model Name</label>
            <input
              type="text"
              className="form-input"
              value={settings.llama_cpp_model}
              onChange={(e) => setSettings({...settings, llama_cpp_model: e.target.value})}
              placeholder="default"
            />
          </div>
          <button type="submit" className="btn btn-success">Save LLM Settings</button>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Email Configuration</h3>
        <form onSubmit={handleEmailUpdate}>
          <div className="grid grid-2">
            <div className="form-group">
              <label className="form-label">SMTP Host</label>
              <input
                type="text"
                className="form-input"
                value={settings.email_smtp_host}
                onChange={(e) => setSettings({...settings, email_smtp_host: e.target.value})}
                placeholder="smtp.example.com"
              />
            </div>
            <div className="form-group">
              <label className="form-label">SMTP Port</label>
              <input
                type="number"
                className="form-input"
                value={settings.email_smtp_port}
                onChange={(e) => setSettings({...settings, email_smtp_port: parseInt(e.target.value)})}
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">From Address</label>
            <input
              type="email"
              className="form-input"
              value={settings.email_from}
              onChange={(e) => setSettings({...settings, email_from: e.target.value})}
              placeholder="noreply@example.com"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-input"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              placeholder="SMTP password"
            />
          </div>
          <button type="submit" className="btn btn-success">Save Email Settings</button>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Branding</h3>
        <form onSubmit={handleBrandingSave}>
          <div className="form-group">
            <label className="form-label">System Name</label>
            <input
              type="text"
              className="form-input"
              value={brandingForm.system_name}
              onChange={(e) => setBrandingForm({...brandingForm, system_name: e.target.value})}
              placeholder="Workflow System"
            />
          </div>
          <button type="submit" className="btn btn-success">Save Branding</button>
        </form>

        <div style={{ marginTop: '1rem' }}>
          <label className="form-label">Logo</label>
          {logoPreview && (
            <div style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <img src={logoPreview} alt="Logo preview" className="brand-logo" style={{ height: '48px' }} />
              <button type="button" className="btn btn-sm btn-danger" onClick={handleLogoRemove}>Remove</button>
            </div>
          )}
          <input type="file" accept="image/*" className="form-input" onChange={handleLogoUpload} />
          <small style={{ color: '#7f8c8d' }}>PNG, JPG, SVG, GIF, or WebP. Shown in the navbar and login page.</small>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Offerings Banner</h3>
        <p style={{ color: '#7f8c8d', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Optional banner displayed at the top of the Offerings page for important notices. Hidden when disabled.
        </p>
        <form onSubmit={handleBannerSave}>
          <div className="form-group" style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={bannerForm.banner_enabled}
                onChange={(e) => setBannerForm({ ...bannerForm, banner_enabled: e.target.checked })}
                style={{ width: '18px', height: '18px' }}
              />
              <span className="form-label" style={{ margin: 0 }}>Show Banner on Offerings Page</span>
              {bannerForm.banner_enabled && (
                <span className="badge badge-success" style={{ marginLeft: '0.5rem' }}>Visible</span>
              )}
            </label>
          </div>

          <div className="form-group">
            <label className="form-label">Title</label>
            <input
              type="text"
              className="form-input"
              value={bannerForm.banner_title}
              onChange={(e) => setBannerForm({ ...bannerForm, banner_title: e.target.value })}
              placeholder="Important Notice"
              disabled={!bannerForm.banner_enabled}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Message</label>
            <textarea
              className="form-textarea"
              value={bannerForm.banner_message}
              onChange={(e) => setBannerForm({ ...bannerForm, banner_message: e.target.value })}
              placeholder="System maintenance scheduled for..."
              rows={3}
              disabled={!bannerForm.banner_enabled}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Banner Color</label>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                type="color"
                value={bannerForm.banner_color}
                onChange={(e) => setBannerForm({ ...bannerForm, banner_color: e.target.value })}
                disabled={!bannerForm.banner_enabled}
                style={{ width: '48px', height: '36px', border: 'none', cursor: 'pointer' }}
              />
              <input
                type="text"
                className="form-input"
                value={bannerForm.banner_color}
                onChange={(e) => setBannerForm({ ...bannerForm, banner_color: e.target.value })}
                disabled={!bannerForm.banner_enabled}
                style={{ maxWidth: '120px' }}
              />
              <div style={{ width: '100%', height: '4px', backgroundColor: bannerForm.banner_color, borderRadius: '2px' }} />
            </div>
          </div>

          <button type="submit" className="btn btn-success">Save Banner Settings</button>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Marketplace Categories</h3>
        <p style={{ color: '#7f8c8d', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Manage the categories available when publishing workflows or nodes to the marketplace.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
          {marketplaceCategories.map(cat => (
            <span key={cat} style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
              backgroundColor: '#ecf0f1', padding: '0.35rem 0.75rem', borderRadius: '20px',
              fontSize: '0.85rem'
            }}>
              {cat}
              <button
                onClick={() => handleRemoveCategory(cat)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#e74c3c', fontSize: '1rem', lineHeight: 1, padding: 0 }}
                title="Remove category"
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <form onSubmit={handleAddCategory} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            className="form-input"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            placeholder="New category name"
            style={{ flex: 1 }}
          />
          <button type="submit" className="btn btn-primary" disabled={!newCategory.trim()}>Add</button>
        </form>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="card-title">Incoming Email Monitor (IMAP)</h3>
        <p style={{ color: '#7f8c8d', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Monitor an email inbox for incoming messages. Emails containing <code>{`{Rule####}`}</code> in the subject or body will trigger the matching workflow ID.
          Emails without a rule tag will trigger the default workflow (if configured). Processed emails are moved to the trash folder.
        </p>
        <form onSubmit={handleImapUpdate}>
          <div className="form-group" style={{ marginBottom: '0.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={imapSettings.imap_monitor_enabled}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_monitor_enabled: e.target.checked })}
                style={{ width: '18px', height: '18px' }}
              />
              <span className="form-label" style={{ margin: 0 }}>Enable IMAP Monitor</span>
              {imapSettings.imap_monitor_enabled && (
                <span className="badge badge-success" style={{ marginLeft: '0.5rem' }}>Active</span>
              )}
            </label>
          </div>

          <div className="grid grid-2">
            <div className="form-group">
              <label className="form-label">IMAP Host</label>
              <input
                type="text"
                className="form-input"
                value={imapSettings.imap_host}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_host: e.target.value })}
                placeholder="imap.gmail.com"
              />
            </div>
            <div className="form-group">
              <label className="form-label">IMAP Port</label>
              <input
                type="number"
                className="form-input"
                value={imapSettings.imap_port}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_port: parseInt(e.target.value) || 993 })}
              />
            </div>
          </div>

          <div className="grid grid-2">
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                value={imapSettings.imap_username}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_username: e.target.value })}
                placeholder="user@example.com"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password / App Password</label>
              <input
                type="password"
                className="form-input"
                value={imapPassword}
                onChange={(e) => setImapPassword(e.target.value)}
                placeholder="IMAP password"
              />
            </div>
          </div>

          <div className="grid grid-4">
            <div className="form-group">
              <label className="form-label">Source Folder</label>
              <input
                type="text"
                className="form-input"
                value={imapSettings.imap_folder}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_folder: e.target.value })}
                placeholder="INBOX"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Trash Folder</label>
              <input
                type="text"
                className="form-input"
                value={imapSettings.imap_trash_folder}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_trash_folder: e.target.value })}
                placeholder="Trash"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Poll Interval (seconds)</label>
              <input
                type="number"
                className="form-input"
                value={imapSettings.imap_poll_interval}
                onChange={(e) => setImapSettings({ ...imapSettings, imap_poll_interval: parseInt(e.target.value) || 300 })}
                min={30}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Default Workflow ID (no rule tag)</label>
            <input
              type="text"
              className="form-input"
              value={imapSettings.imap_default_workflow_id}
              onChange={(e) => setImapSettings({ ...imapSettings, imap_default_workflow_id: e.target.value })}
              placeholder="e.g. 5 (leave empty to send error email instead)"
            />
            <small style={{ color: '#7f8c8d' }}>Workflow triggered when an email has no {`{Rule####}` } tag. Leave empty to notify admins via email instead.</small>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button type="submit" className="btn btn-success">Save IMAP Settings</button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleImapTest}
              disabled={imapTesting}
            >
              {imapTesting ? 'Testing...' : 'Test Connection'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleImapPollNow}
              disabled={imapPolling || !imapSettings.imap_monitor_enabled}
            >
              {imapPolling ? 'Polling...' : 'Poll Now'}
            </button>
          </div>
        </form>

        {imapTestResult && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: imapTestResult.connected ? '#d4edda' : '#f8d7da', borderRadius: '4px' }}>
            <strong>{imapTestResult.connected ? 'Connected' : 'Connection Failed'}</strong>
            {imapTestResult.error && (
              <div style={{ marginTop: '0.5rem' }}>{imapTestResult.error}</div>
            )}
            {imapTestResult.unseen_count !== undefined && (
              <div style={{ marginTop: '0.5rem' }}>
                Unseen emails in {imapTestResult.folder}: <strong>{imapTestResult.unseen_count}</strong>
              </div>
            )}
            {imapTestResult.preview && imapTestResult.preview.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong>Preview (first 10):</strong>
                <table style={{ width: '100%', marginTop: '0.5rem', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #ccc' }}>
                      <th style={{ textAlign: 'left', padding: '4px' }}>From</th>
                      <th style={{ textAlign: 'left', padding: '4px' }}>Subject</th>
                      <th style={{ textAlign: 'left', padding: '4px' }}>Rule Tag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {imapTestResult.preview.map((item: any, i: number) => (
                      <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: '4px' }}>{item.from}</td>
                        <td style={{ padding: '4px' }}>{item.subject}</td>
                        <td style={{ padding: '4px' }}><code>{item.rule_tag}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
